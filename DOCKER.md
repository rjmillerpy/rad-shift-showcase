# Running RadShift in Docker

Three containers, started together by `compose.yaml`:

```
browser ──► frontend  (Next.js, localhost:3000)
browser ──► backend   (FastAPI, localhost:5000) ──► db (Postgres 16, localhost:5433)
```

The browser calls **both** the frontend and the backend directly (axios runs
in the browser), which is why the backend port is published and why the
frontend is built with `NEXT_PUBLIC_API_URL=http://localhost:5000`.

## Prerequisites

- Docker Engine with the Compose plugin (`docker compose version`)
- This repo and `rad-shift-frontend` cloned side by side
- A `.env` in this repo (copy `.env.example`). Inside Compose, the `DB_*`
  values are overridden to point at the bundled Postgres.
- Optional: `~/.aws/credentials` for S3 uploads (mounted read-only)

## Everyday commands

```bash
docker compose up --build          # build images, start all three, stream logs
docker compose up --build -d       # same, in the background
docker compose ps                  # what's running, health status
docker compose logs -f backend     # follow one service's logs
docker compose exec backend sh     # shell inside the running backend
docker compose stop                # stop (containers kept)
docker compose down                # remove containers (database volume kept)
docker compose down -v             # remove containers AND the database volume
```

Rebuild one service after code changes: `docker compose up --build backend`.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Backend image, multi-stage: a `builder` stage runs `uv sync` from uv.lock; the `runtime` stage (python:3.12-slim + ffmpeg + Playwright headless browsers) copies in only the virtualenv and the files the app reads. Runs as non-root uid 1000; the code is root-owned and read-only to it |
| `docker-entrypoint.sh` | Runs `scripts/prepare_db.py`, then `exec`s uvicorn |
| `scripts/prepare_db.py` | Empty DB: create schema from models + `alembic stamp head`. Existing DB: `alembic upgrade head` |
| `.dockerignore` | Keeps `.env`, `.venv`, tests, caches and node_modules out of the build context (the Dockerfile also copies an explicit list, not `COPY . .`) |
| `compose.yaml` | Wires db + backend + frontend, healthchecks, volume, ports |
| `compose.tls.yaml` + `caddy/Caddyfile` | Opt-in HTTPS: Caddy in front as the only way in (see below) |
| `compose.observability.yaml` + `observability/` | Opt-in metrics, logs, dashboard and alert email (see below) |
| `../rad-shift-frontend/my-social-feed/Dockerfile` | Multi-stage Next.js build → standalone `server.js` |
| `../rad-shift-frontend/my-social-feed/.dockerignore` | Keeps node_modules, .next, tests, `.env*` out of the build |

## HTTPS through a reverse proxy (Caddy)

The same stack behind Caddy, the way it runs behind the load balancer at
go-live: TLS ends at the proxy, the host name picks the service, and the
backend and frontend no longer publish ports.

```sh
docker compose -f compose.yaml -f compose.tls.yaml up --build -d
# https://app.localhost   (frontend)
# https://api.localhost   (API)
```

`*.localhost` always points at your own machine, so there's no DNS to set
up and no domain to buy. Certificates come from Caddy's local CA, which is
created on first start and kept in the `caddy_data` volume. Until you trust
it, browsers warn about the certificate. To trust it on this machine:

```sh
docker compose -f compose.yaml -f compose.tls.yaml cp \
  caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
curl --cacert caddy-root.crt https://api.localhost/health   # verifies the certificate
# Chrome/Firefox on Linux: Settings > Certificates > Authorities > Import caddy-root.crt
```

Only trust it on your own machine. The CA's private key is in that volume,
and anyone holding it can issue certificates your browser accepts. Delete
`caddy-root.crt` afterwards; it is not a secret, but it doesn't belong in the
repo.

Test it: `E2E_TLS=1 e2e/run.sh` runs the whole e2e suite through the proxy,
plus `e2e/test_tls_proxy.py`, which checks:
- the certificate verifies against the local CA;
- http redirects to https;
- the security headers (HSTS, nosniff, referrer policy) are set and the
  `Server` header is hidden;
- ports 3000 and 5000 are closed;
- uvicorn logs the real client, not Caddy and not a spoofed
  `X-Forwarded-For`.

At go-live the ALB does this job, with a free ACM certificate for the real
domain (item 14 in the roadmap: ~$15/year for the domain, $0.50/month for the
hosted zone). DuckDNS is the free option if the local stack ever needs a
public name; Caddy then gets a real Let's Encrypt certificate.

## Metrics, logs and alerts

Six more containers: Prometheus (metrics and alert rules), Alertmanager
(sends the alerts), Mailpit (catches the emails), Loki (stores logs), Alloy
(ships container logs to Loki) and Grafana (dashboard). All free, all on
127.0.0.1.

```sh
docker compose -f compose.yaml -f compose.observability.yaml up --build -d
# http://localhost:3001   Grafana: the rad-shift dashboard opens by default
# http://localhost:9090   Prometheus: Status > Targets, Alerts, ad-hoc queries
# http://localhost:9093   Alertmanager: what is firing, silences
# http://localhost:8025   Mailpit: the alert emails
```

Add `-f compose.tls.yaml` to have both. Grafana's admin login is
`admin` / `radshift-local` (set `GRAFANA_ADMIN_PASSWORD` to change it);
viewing needs no login.

How the pieces connect:

```
backend /metrics ──scrape every 15 s──► Prometheus ──alert rules──► Alertmanager ──SMTP──► Mailpit
container stdout ──Docker socket──► Alloy ──push──► Loki
                                     Grafana reads Prometheus, Loki and Alertmanager
```

Try an alert: `docker compose stop backend`. BackendDown fires after a minute
of failed scrapes and the email shows up in Mailpit about two minutes after
the stop. `docker compose start backend` sends the "resolved" email.

Things worth knowing:
- **Alloy reads the Docker socket**, and read-only doesn't make that safe:
  anything that can talk to the socket can start a privileged container.
  Fine on your laptop; on ECS the awslogs driver collects logs with no socket.
- **Loki has no healthcheck**: its image is distroless (no shell, no wget).
  Alloy and Grafana retry until it is ready.
- **Dashboards are files.** Edits in the Grafana UI are lost on restart:
  export the JSON over `observability/grafana/dashboards/rad-shift.json`
  and commit it.
- **Check configs** with `observability/check.sh`: promtool, amtool, Loki
  and Alloy validate their own files, and `promtool test rules` runs the
  alert rule tests in `observability/prometheus/alerts.test.yml`.
- **Test it** with `E2E_OBS=1 e2e/run.sh`: scrapes, route labels, rules
  loaded, logs reaching Loki through Grafana, the dashboard, and a real
  drill that stops the API and waits for the email.

## Things that commonly trip people up

- **`localhost` inside a container means that container.** The backend reaches
  Postgres at `db:5432` (service name + container port), not `localhost:5433`.
- **`NEXT_PUBLIC_*` is baked in at build time.** Changing the API URL means
  rebuilding the frontend image, not just restarting it.
- **Published vs internal ports.** `127.0.0.1:5433:5432` means host port 5433 →
  container port 5432. Other containers always use 5432.
- **`$` in `.env` values.** Compose reads `.env` and treats `$name` as a
  variable reference (you'll see `The "name" variable is not set` warnings and
  a mangled value). Wrap such values in single quotes: `KEY='pa$$word'`.
  python-dotenv reads single-quoted values literally too.
- **One uvicorn worker.** Each worker would start its own generator scheduler.
- **Smaller backend image:** `INSTALL_BROWSERS=false` skips Playwright's
  Chromium/Firefox (~1 GB). Generator sources with `use_browser` will then fail.
- **Widget server execution stays off** (`WIDGET_SERVER_EXECUTION_ENABLED=false`).
  It is not a sandbox; see `app/widgets/executor.py`.
