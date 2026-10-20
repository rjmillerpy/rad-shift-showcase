# rad-shift

A social app where one stream of posts is shown through many "skins": a classic
feed, bubbles, a forum, a mosaic, a spreadsheet ledger, an LLM-narrated
chronicle, and Amble, a Phaser town you walk around in where signs and
shopkeepers read you posts. This is the FastAPI backend; the Next.js frontend
is [rad-shift-frontend-showcase](https://github.com/rjmillerpy/rad-shift-frontend-showcase).

## This repository is the open-core mirror

rad-shift is developed in private repositories, which run production. This
public mirror is exported from them automatically on every push to `main`,
from an allowlist of paths, so what you see is the real code, infrastructure,
CI/CD and tests. It is read-only; issues and pull requests are off. Its git history starts at the split (older commits held the private code); [BUILD_LOG.md](BUILD_LOG.md) records how it got here.

A few parts stay private. The app reaches them through one seam,
[`app/plugins.py`](app/plugins.py): an **edition** supplies them, and this
repository runs the public one ([`app/baseline.py`](app/baseline.py)), which
works end to end:

| | Production (private edition) | This repository (public edition) |
|---|---|---|
| Content generators | Reddit, X and Pinterest sources, plus any site scraped by CSS selector (a headless browser, with Claude writing and repairing the selectors) | RSS/Atom feeds ([`rss.py`](app/generators/platforms/rss.py)) |
| Chronicle narration | the production narration prompt | a plain prompt asking for the same JSON segments ([`prompt.py`](app/chronicle/prompt.py)) |
| Admin console | moderation, analytics, custom graphs, Amble binding editor (`/admin`) | none |
| Amble's town | the production town's content bindings | a small demo town ([`demo-bindings.yaml`](app/amble/content/demo-bindings.yaml)) |

Production sets `RADSHIFT_EDITION=private`, so a missing private package fails
at startup instead of quietly falling back to this edition.

## Run it
1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker.
2. `cp .env.example .env`, fill in the values, `chmod 600 .env`.
3. `docker compose up --build --wait` starts Postgres, this API on :5000 and the frontend on :3000 (with the frontend repository cloned next to this one). [DOCKER.md](DOCKER.md) has the details.

Without Docker: `uv sync --all-groups`, then `uv run uvicorn app.main:app --reload --port 5000` against a Postgres of your own.

## CI
Every push runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml): **lint** (the pre-commit hooks below) and **test** (pytest, ~2,400 tests on in-memory SQLite) in parallel, then **build** the Docker image once both pass.

**Tests: 2,874 · coverage 96% (lines + branches; CI fails below 95%).** The test job runs the suite in parallel with pytest-xdist, then the timing-sensitive `perf` tests alone so other workers can't skew them. The coverage table is in each run's summary page.

Test-suite time, same machine: **397 s → 96 s** from using bcrypt's minimum cost in tests (production keeps 12; a test guards it) **→ 24 s** with `-n auto` (16 cores). On CI (2-core runners, with coverage on) the test step went from about 10 min to 3 min 30 s (195 s parallel + 15 s perf), and the whole CI run from 13.5 min to 5.9 min.

Run the same checks locally:
```bash
uv sync --all-groups && source .venv/bin/activate
pre-commit run --all-files   # what the lint job runs
pytest -q -n auto            # parallel; drop -n auto to debug with pdb
pytest -q -n auto --cov      # with the coverage table
docker build -t radshift-backend .
```

## Health checks
| Endpoint | Answers | Use it for |
|---|---|---|
| `GET /health` | 200 `{"status":"ok","checks":{"database":"ok"}}`, or 503 when `SELECT 1` fails | readiness: load balancer target checks, Docker/Compose `healthcheck`, deploy gates |
| `GET /health/live` | 200 `{"status":"ok"}` whenever the process is serving | liveness: "should this container be restarted?" It never touches the database, so a database outage doesn't restart healthy containers |

Both are unauthenticated and uncached, and a failure's detail goes to the log, not the response. `compose.yaml` uses `/health` for the backend and the frontend's `/api/health` for the frontend, so `docker compose up --wait` returns only when the whole stack can serve. Measured with `docker compose stop db`: `/health` returns 503 at once, Docker marks the backend unhealthy within ~30 s and healthy again ~10 s after the database returns, with no restart.

## Continuous delivery
Each commit on `main` that passes CI is built into an image, pushed to ECR tagged with its commit SHA, and deployed to the local stack by a self-hosted runner: health-gated, with automatic rollback, and any SHA still in ECR can be deployed by hand. About 5-10 cents a month, no Actions minutes. [DEPLOY.md](DEPLOY.md) has the setup and the runbook.

## Code quality
SonarQube Cloud analyses both private repositories on every push to `main` and every pull request, on a self-hosted runner. Its Quality Gate is "Sonar way". On new code it requires: no new issues, every security hotspot reviewed, at least 80% coverage (from the pytest and Jest reports) and at most 3% duplicated lines. A failed gate fails the job and shows on the pull request. The free plan covers private code up to 50,000 lines; both repositories together are about 42,000 (tests don't count).

Self-hosted, for comparison (roadmap item 19): `scripts/sonarqube-local.sh` starts SonarQube Community Build and Postgres (`compose.sonarqube.yaml`, `127.0.0.1:9000`, about 2-3 GB of RAM) and scans both repositories. `--with-tests` refreshes the coverage reports first. Same engine and the same numbers for lines, coverage and duplication. But it reports about 1,100 more issues, for two reasons. First, its default profile is the full "Sonar way" (about 400-435 rules per language), while the Cloud organization uses "Sonar way core" (about 250-300). Second, accepted and false-positive decisions live on the server, not in the code. Community Build also has no pull-request or branch analysis, and you run its upgrades, database and backups yourself. That's why Cloud is the one in CI.

## Security scanning
Free stand-ins for commercial SAST/SCA such as Veracode (roadmap item 21). `scripts/security-scan.sh` runs locally, and `.github/workflows/security.yml` runs the same script on every push to `main`, on pull requests and weekly, because new CVEs appear against unchanged code.

- **Semgrep** (1.179.0, pinned image, `--metrics=off`) checks the code with the curated `p/default` rules plus the Python, TypeScript and React packs. Exceptions are `nosemgrep` comments with the reason.
- **pip-audit** checks both lockfiles (the app's and Checkov's tool environment); the frontend runs `npm audit` on its production dependencies.
- **Grype** (v0.120.0) scans each image in `publish.yml` before it is pushed, and fails on any critical CVE that has a fix. `.grype.yaml` lists the temporary exceptions, each with its reason and end date. Install it checksum-verified from the [release page](https://github.com/anchore/grype/releases) into `~/.local/bin`.
- **Not used:** CodeQL (GitHub allows it on private repositories only with the paid Advanced Security) and Trivy (its releases were hijacked in March 2026, CVE-2026-33634).

## Feature flags
Releases are separate from deploys: [`flags/flags.flagd.json`](flags/README.md) is served by flagd and evaluated in-process through OpenFeature (`app/flags/`). Saving the file changes behaviour within a second, with no restart. Chronicle's Claude narration rolls out to admins plus 10% of signed-in users, and server-side widget execution has a runtime kill switch. Each flag has a safe fallback in code for when flagd is down.

## Observability
`docker compose -f compose.yaml -f compose.observability.yaml up --build -d` adds metrics, logs, a dashboard and alert email to the local stack, all free and self-hosted ([DOCKER.md](DOCKER.md#metrics-logs-and-alerts) has the walkthrough).

- **Metrics:** `GET /metrics` (`app/metrics/`) exports a request counter and a latency histogram labelled by **route template** (`/posts/{post_id}`, never `/posts/123`), so the number of time series is fixed by the code, not by traffic. Prometheus scrapes it on the compose network; Caddy and the ALB never expose it, and on AWS the route doesn't exist (`METRICS_ENABLED=false`).
- **Logs:** Grafana Alloy ships every container's output to Loki.
- **Dashboard:** Grafana, provisioned from `observability/grafana/` (request rate, 5xx rate, p95 latency, memory, logs).
- **Alerts:** `HighServerErrorRate` (over 5% 5xx for 5 minutes, with a traffic floor) and `BackendDown` (failed scrapes for 1 minute: a dead API has no error rate, only missing data). Alertmanager emails Mailpit, a local mail catcher. The rules have `promtool` unit tests.
- **Drills (real stack):** API stopped → BackendDown email in **115 s**. Database stopped → HighServerErrorRate email in **7 min 47 s** (the 5-minute `for:`, plus scrape, evaluation and Alertmanager's 30 s `group_wait`); database back → resolved email in **5 min 2 s** (the 5-minute rate window has to drain the 503s).
- **At go-live:** the same two alarms in CloudWatch on the ALB's free metrics, to SNS email (`infra/monitoring.tf`, about $0.30/month), and logs in CloudWatch Logs.

`observability/check.sh` validates every config with its own tool (and runs the rule tests) in the pinned images; CI runs it when those files change. `tests/test_observability_config.py` catches drift: dashboard queries for metrics the app doesn't export, a threshold that differs between Prometheus and CloudWatch, unpinned images, UIs listening beyond localhost.

## Docker image
[`Dockerfile`](Dockerfile) is multi-stage: `builder` installs the locked dependencies with uv, and `runtime` copies in only the virtualenv plus `app/`, `scripts/`, `alembic/`, `alembic.ini` and the entrypoint. No uv, lockfile, tests or local caches reach the final image. It runs as non-root uid 1000, and the code is root-owned, so the app can read but not change it (runtime writes go to `/tmp`).

| Image | Before | After |
|---|---|---|
| Production (private edition, with scraping browsers), compressed | 811 MB | **617 MB** |
| Production, on disk | 2.92 GB | **2.26 GB** |
| Without browsers (as this public edition builds), compressed | 312 MB | **302 MB** |
| App code in the image (`/app`) | 53 MB | **1.1 MB** |

Where it came from: Chromium's headless shell only (`--only-shell`; the app never launches a headed browser, and the full browser was 393 MB), and an explicit `COPY` list instead of `COPY . .`, which had been shipping a 48 MB `.mypy_cache`. Considered and declined: copying `ffprobe` and the 210 libraries it links out of a build stage instead of `apt install ffmpeg` (457 MB) would save about 240 MB, but files outside the package database are invisible to image vulnerability scanners.

## Infrastructure
[`infra/`](infra/README.md) describes the AWS deployment (ECS Fargate, ALB, IAM, and the database as Neon or RDS) as Terraform. It is validated, tested offline (35 `terraform test` runs against a mock provider, plus tflint and Checkov, in CI) and planned against the real account, but not applied: nothing that costs more than pennies is created until the app goes live.

## Secrets
[`.env.example`](.env.example) lists every variable the backend reads, split into configuration and secrets; `tests/test_env_example.py` fails if code and file drift apart, or if its secrets differ from what ECS injects. Locally the values live in `.env` (gitignored; keep it `chmod 600`). The app refuses to start with a `JWT_SECRET` under 32 bytes.

| Secret | Local | CI | Go-live | Rotate by | If it leaks |
|---|---|---|---|---|---|
| `JWT_SECRET` | `.env` | generated per run (`e2e/run.sh`) | SSM `/radshift/JWT_SECRET` | new value (`openssl rand -hex 32`), sync, redeploy | anyone can mint login tokens; rotating logs everyone out |
| `DB_PASSWORD` | `.env` | throwaway compose DB | SSM, or RDS-managed (rotated by RDS) | change in the DB, then sync + redeploy | full database access |
| `ADMIN_SECRET` | `.env` | — | SSM | new value, sync, redeploy | any user can make themselves admin |
| `ANTHROPIC_API_KEY`, `RESEND_API_KEY` | `.env` | — | SSM | new key in the provider console, sync, revoke the old one | spend on your account / email sent as you |
| `FRONTEND_DEPLOY_KEY` / `BACKEND_DEPLOY_KEY` | `~/.ssh/radshift-ci/` | GitHub Actions secrets | same | new key pair, replace deploy key + secret | read-only clone of the other repo |
| `radshift-app` AWS key | `~/.aws/credentials` | — | none: the ECS task role replaces it | new access key, delete the old | 4 S3 actions on one bucket |

Loading the go-live values (SecureString, Standard tier: free; values are never printed):
```bash
python scripts/sync_ssm_secrets.py --check --profile radshift-admin                                # read-only: which exist?
python scripts/sync_ssm_secrets.py --apply --env-file .env.production --profile radshift-admin     # write / rotate
```
Its tests run against Moto's in-memory AWS, so CI needs no credentials.

## Dependencies
Declared in [`pyproject.toml`](pyproject.toml) (`[project]` for the app, `[dependency-groups]` for `dev` and `e2e`); every resolved version, transitive ones included, is in [`uv.lock`](uv.lock). Commit both.
```bash
uv add <pkg>==<version>        # app dependency (pins are exact on purpose)
uv add --group dev <pkg>       # test/lint tool
uv lock --upgrade-package <pkg> # bump one package
uv sync --all-groups           # make .venv match uv.lock exactly (removes strays)
```
CI and the Dockerfile install with `--locked`, which fails if `pyproject.toml` was edited without re-running `uv lock`. The uv version is pinned in the Dockerfile's `uv` stage (Dependabot bumps it) and in the `setup-uv` steps of `ci.yml` and `integration.yml` (bump those by hand to match).

Install speed, same machine, cold: `pip install -r requirements-dev.txt` 21.0 s → `uv sync` 2.1 s. Docker dependency layer: 12.3 s → 5.8 s; image 1.27 GB → 1.22 GB (without browsers).

## Code quality
[`pre-commit`](.pre-commit-config.yaml) runs the same checks before every commit and in CI: **ruff** (lint + format, line length 100), **mypy**, and file hygiene (whitespace, YAML/TOML, merge markers, private keys). Install the git hook once per clone with `pre-commit install`, with `.venv` activated (mypy runs from it).

- **Lint rules** are pinned in `pyproject.toml` and widened one family at a time: core errors, imports (`I`), pyupgrade (`UP`), bugbear (`B`), simplify (`SIM`), comprehensions (`C4`).
- **mypy uses a ratchet:** modules with known type debt (old-style SQLAlchemy `Column` models) are listed in `pyproject.toml` and skipped. Every other module, and any new one, must type-check. The list may only shrink.
- **Bandit** scans `app/` and `scripts/` for security issues on every commit and in CI (settings in `[tool.bandit]`). Accepted findings carry `# nosec <ID> - <reason>`; test code is excluded because pytest relies on `assert`.
- **Trufflehog** blocks secrets in three layers: the pre-commit hook scans staged files (install the [trufflehog binary](https://github.com/trufflesecurity/trufflehog/releases) on your PATH), the CI `secrets` job scans each push, and [`secret-scan.yml`](.github/workflows/secret-scan.yml) rescans the full history weekly. Any detection fails, verified or not.
- **Dependabot** (configured in the private repositories; this mirror gets no dependency PRs) opens weekly PRs for pip, the Docker base image, compose images and GitHub Actions; minor/patch updates are grouped to save CI minutes, and each PR runs CI + Integration. Deliberate majors (pydantic 2, PyJWT 2, Python, Postgres) are held back. Vulnerability alerts and security-fix PRs are on.
- The one-off formatting commit is in `.git-blame-ignore-revs`; run `git config blame.ignoreRevsFile .git-blame-ignore-revs` once so `git blame` skips it.

**Integration:** [`.github/workflows/integration.yml`](.github/workflows/integration.yml) starts the full stack (Postgres + this API + the frontend repo's `main`) with Docker Compose and drives it with a real browser: sign up, verify, log in, post, like. Runs on pushes to `main`, PRs, and on demand. See [`e2e/README.md`](e2e/README.md) to run it locally.
