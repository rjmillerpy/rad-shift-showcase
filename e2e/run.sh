#!/usr/bin/env bash
# Run the end-to-end suite against the full stack (Postgres + API + Next.js).
#
#   e2e/run.sh                 # build, start, test, tear down
#   e2e/run.sh -k like         # extra args go to pytest
#   E2E_HEADED=1 e2e/run.sh    # watch the browser (local only)
#   E2E_TLS=1 e2e/run.sh       # the same suite over HTTPS through Caddy (compose.tls.yaml)
#   E2E_OBS=1 e2e/run.sh       # plus Prometheus, Loki, Grafana and alert email (compose.observability.yaml)
#
# Needs rad-shift-frontend checked out next to this repo (same layout as
# compose.yaml expects) and the e2e dependency group (`uv sync --all-groups`).
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=radshift-e2e   # separate containers, images, and DB volume from your local stack
COMPOSE_FILES="compose.yaml:e2e/compose.e2e.yaml"
APP_URL=http://localhost:3000
API_URL=http://localhost:5000
PORTS=(3000 5000 5433)
if [ "${E2E_TLS:-0}" = "1" ]; then
  # Caddy is the only way in; the app's own ports are not published.
  COMPOSE_FILES="$COMPOSE_FILES:compose.tls.yaml"
  APP_URL=https://app.localhost
  API_URL=https://api.localhost
  PORTS=(80 443 5433)
fi
if [ "${E2E_OBS:-0}" = "1" ]; then
  COMPOSE_FILES="$COMPOSE_FILES:compose.observability.yaml"
  PORTS+=(3001 8025 9090 9093)
fi
compose_args=()
IFS=: read -ra files <<< "$COMPOSE_FILES"
for f in "${files[@]}"; do compose_args+=(-f "$f"); done
compose() { docker compose -p "$PROJECT" "${compose_args[@]}" "$@"; }

# The stack publishes fixed ports (the browser bundle has its API URL baked
# in), so a running local stack would collide with the test stack.
for port in "${PORTS[@]}"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is already in use. Stop your local stack first: docker compose stop" >&2
    exit 1
  fi
done

# CI has no .env. Generate a throwaway one, and never touch a real one.
created_env=0
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
  created_env=1
fi

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    compose logs --no-color > e2e-stack.log 2>&1 || true
    echo "Tests failed; container logs saved to e2e-stack.log" >&2
  fi
  compose down -v --remove-orphans > /dev/null 2>&1 || true
  if [ "$created_env" -eq 1 ]; then rm -f .env; fi
  rm -f "${ca_file:-}"
  exit "$status"
}
trap cleanup EXIT

# --wait returns once every service is healthy: Postgres accepts connections,
# the API's /health can reach it, and the frontend answers /api/health.
echo "== Building and starting the stack"
compose up -d --build --wait

ca_file=""
if [ "${E2E_TLS:-0}" = "1" ]; then
  # The local CA's root, so the API tests verify certificates instead of
  # skipping verification. (The browser ignores HTTPS errors instead:
  # Chromium only trusts roots installed in an NSS database.)
  ca_file="$(mktemp --suffix=.crt)"
  compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$ca_file" > /dev/null
fi

headed=()
if [ "${E2E_HEADED:-0}" = "1" ]; then headed=(--headed --slowmo 300); fi

echo "== Running the e2e suite"
# The resilience test restarts this stack's database through Compose.
E2E_COMPOSE_PROJECT="$PROJECT" E2E_COMPOSE_FILES="$COMPOSE_FILES" \
E2E_API_URL="$API_URL" E2E_TLS_CA="$ca_file" E2E_OBS="${E2E_OBS:-0}" \
python -m pytest e2e \
  --base-url "$APP_URL" \
  --browser chromium \
  --tracing retain-on-failure \
  --screenshot only-on-failure \
  --output test-results \
  "${headed[@]}" "$@"
