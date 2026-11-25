#!/usr/bin/env bash
# Load the DAGs the way the scheduler does and run their tests, inside the
# Airflow image (its test stage adds pytest):
#
#   orchestration/check.sh
#
# Needs Docker only; nothing is started but the one test container.
set -euo pipefail
cd "$(dirname "$0")/.."

docker build -q -f orchestration/Dockerfile --target test -t radshift-airflow:test . > /dev/null
docker run --rm \
  -v "$PWD/orchestration:/opt/orchestration:ro" \
  -e AIRFLOW__CORE__LOAD_EXAMPLES=false \
  -e AIRFLOW__CORE__UNIT_TEST_MODE=true \
  --entrypoint bash radshift-airflow:test -c \
  "airflow db migrate > /dev/null && python -m pytest -q -p no:cacheprovider /opt/orchestration/tests"
