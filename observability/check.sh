#!/usr/bin/env bash
# Validate the observability configs with each tool's own checker, inside the
# images compose.observability.yaml pins (one source for the versions):
#
#   observability/check.sh
#
# Includes the alert rules' unit tests (prometheus/alerts.test.yml). Needs
# Docker only; CI runs it in the observability job.
set -euo pipefail
cd "$(dirname "$0")/.."

# A project of its own, removed at the end with the volumes `run` creates.
compose() { docker compose -p radshift-check -f compose.observability.yaml "$@"; }
trap 'compose down -v > /dev/null 2>&1 || true' EXIT

run() {
  local service=$1 entrypoint=$2
  shift 2
  compose run --rm --no-deps -T --quiet-pull \
    -v "$PWD/observability:/check:ro" --entrypoint "$entrypoint" "$service" "$@"
}

echo "== Prometheus config"
# --syntax-only: the rule file path inside prometheus.yml is the container's.
run prometheus promtool check config --syntax-only /check/prometheus/prometheus.yml
echo "== Alert rules"
run prometheus promtool check rules /check/prometheus/alerts.yml
echo "== Alert rule tests"
run prometheus promtool test rules /check/prometheus/alerts.test.yml
echo "== Alertmanager config"
run alertmanager amtool check-config /check/alertmanager/alertmanager.yml
echo "== Loki config"
run loki /usr/bin/loki -config.file=/check/loki/loki.yml -verify-config
echo "== Alloy config"
run alloy /bin/alloy validate /check/alloy/config.alloy
echo "All observability checks passed."
