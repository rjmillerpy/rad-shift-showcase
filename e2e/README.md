# End-to-end (integration) tests

Unit tests in `tests/` fake every boundary: SQLite instead of Postgres, a
mocked API instead of a browser. This suite fakes nothing. It starts the real
stack with Docker Compose and drives it with a real Chromium browser:

```
Playwright (Chromium) ──► Next.js :3000
                      └─► FastAPI :5000 ──► Postgres :5433
```

So it catches the bugs that only exist when the pieces meet: CORS, the API
URL baked into the frontend bundle, JWT handling in the browser, email
verification, and persistence.

| Test | Journey |
|---|---|
| `test_signup_verify_login_post_and_like` | Sign up in the UI → open the verification link → log in → write a post → like it → reload and see the like persisted |
| `test_anonymous_visitor_can_read_but_not_post` | A post made via the API shows up for a logged-out visitor, who gets no "New post" button |

## Run it locally

```bash
# once
uv sync --all-groups     # from the repo root; the e2e group is in pyproject.toml
playwright install chromium

docker compose stop      # the test stack needs ports 3000/5000/5433
e2e/run.sh               # build, start, test, tear down (~1 min when images are cached)
E2E_HEADED=1 e2e/run.sh  # watch the browser do it
E2E_TLS=1 e2e/run.sh     # the same suite over HTTPS through Caddy (compose.tls.yaml)
E2E_OBS=1 e2e/run.sh     # plus metrics, logs, dashboard and an alert drill (~3 min)
e2e/run.sh -k like       # extra args go to pytest
docker compose start     # bring your dev stack back
```

`run.sh` uses its own Compose project (`radshift-e2e`), so your dev database
is never touched, and `compose.e2e.yaml` blanks S3, Resend and Anthropic
settings so a test run can't upload files, send email, or spend API credit,
even with your real `.env` present. If tests fail you get
`test-results/` (screenshots + Playwright traces) and `e2e-stack.log`
(all container logs). Replay a trace with `playwright show-trace <trace.zip>`.

## In CI

`.github/workflows/integration.yml` runs this suite on pushes to `main`, on
pull requests, and on demand. Each repo checks out the *other* repo's `main`:

- here: this branch's backend + frontend `main`
- in rad-shift-frontend: that branch's frontend + backend `main`

### One-time setup: deploy keys

Both repos are private, and a workflow's built-in token can only read its own
repo. Each workflow therefore clones the other repo with a **deploy key**: an
SSH key that grants read-only access to exactly one repository.

Two key pairs (one per direction):

| Key | Public half goes to | Private half goes to |
|---|---|---|
| frontend key | rad-shift-frontend → Settings → Deploy keys (read-only) | rad-shift → Settings → Secrets and variables → Actions → `FRONTEND_DEPLOY_KEY` |
| backend key | rad-shift → Settings → Deploy keys (read-only) | rad-shift-frontend → Settings → Secrets and variables → Actions → `BACKEND_DEPLOY_KEY` |

Generate a pair with `ssh-keygen -t ed25519 -N "" -C "radshift-ci" -f <file>`.
Leave "Allow write access" unticked. If a secret is missing, the workflow's
first step fails with a message pointing here.
