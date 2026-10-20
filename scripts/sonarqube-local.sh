#!/usr/bin/env bash
# Self-hosted SonarQube (roadmap item 19): start it, scan both repositories,
# print where to look. SonarQube Cloud (item 18) stays the analysis in CI;
# this is the run-it-yourself version of the same engine.
#
#   scripts/sonarqube-local.sh               # scan with the coverage reports already on disk
#   scripts/sonarqube-local.sh --with-tests  # run both test suites first (about 3 minutes)
#
# First run: sets a generated admin password (the image ships admin/admin)
# and keeps it in .sonarqube-local (gitignored, mode 600). Each run creates
# an analysis token and revokes it at the end.
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$(cd "$BACKEND/../rad-shift-frontend" && pwd)"
COMPOSE=(docker compose -f "$BACKEND/compose.sonarqube.yaml")
URL=http://127.0.0.1:9000
NETWORK=radshift-sonarqube_default
SCANNER=sonarsource/sonar-scanner-cli:12.2.0.4256_8.1.0
CREDENTIALS="$BACKEND/.sonarqube-local"
TOKEN_NAME="local-scan-$$"
DEFAULT_PASSWORD="admin" # what the image ships with

api() { curl -fsS -u "admin:$ADMIN_PASSWORD" "$@"; }

ensure_admin_password() {
  if [[ -f "$CREDENTIALS" ]]; then
    # shellcheck source=/dev/null
    source "$CREDENTIALS"
    return
  fi
  # Upper, lower, digit and symbol: SonarQube's password policy.
  ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=')Aa1!"
  curl -fsS -u "admin:$DEFAULT_PASSWORD" -X POST "$URL/api/users/change_password" \
    --data-urlencode "login=admin" --data-urlencode "previousPassword=$DEFAULT_PASSWORD" \
    --data-urlencode "password=$ADMIN_PASSWORD"
  (umask 077; printf 'ADMIN_PASSWORD=%q\n' "$ADMIN_PASSWORD" > "$CREDENTIALS")
  echo "Admin password set; it is in $CREDENTIALS"
}

run_tests() {
  echo "== Backend tests (coverage.xml)"
  # --no-build: wheels only; no package build script runs on this machine.
  (cd "$BACKEND" && uv run --no-build pytest -q -n auto -m "not perf" --cov --cov-report=xml:coverage.xml > /dev/null)
  echo "== Frontend tests (coverage/lcov.info)"
  # --no-install: only the jest already in node_modules, never a download.
  (cd "$FRONTEND/my-social-feed" && npx --no-install jest --ci --coverage --silent > /dev/null)
}

# The repository is mounted at its own path, so the absolute file paths in
# the coverage reports match what the scanner sees.
scan() {
  local repo="$1"
  echo "== Scanning $repo"
  docker run --rm --network "$NETWORK" \
    -v "$repo:$repo" -w "$repo" \
    -e SONAR_HOST_URL=http://sonarqube:9000 -e SONAR_TOKEN="$TOKEN" \
    "$SCANNER" \
    -Dsonar.projectBaseDir="$repo" -Dsonar.qualitygate.wait=true \
    -Dsonar.working.directory="$repo/.scannerwork" \
    | grep -E "QUALITY GATE|ANALYSIS SUCCESSFUL|ERROR" || true
}

main() {
  if [[ "${1:-}" == "--with-tests" ]]; then run_tests; fi
  "${COMPOSE[@]}" up -d --wait
  ensure_admin_password
  TOKEN="$(api -X POST "$URL/api/user_tokens/generate" \
    --data-urlencode "name=$TOKEN_NAME" --data-urlencode "type=GLOBAL_ANALYSIS_TOKEN" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])')"
  trap 'api -X POST "$URL/api/user_tokens/revoke" --data-urlencode "name=$TOKEN_NAME" > /dev/null || true' EXIT
  scan "$BACKEND"
  scan "$FRONTEND"
  echo "Done: $URL/projects (admin / the password in $CREDENTIALS)"
}

main "$@"
