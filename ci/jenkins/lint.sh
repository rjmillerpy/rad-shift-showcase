#!/usr/bin/env bash
# Validate the Jenkinsfile with the running Jenkins's own declarative linter:
#
#   ci/jenkins/lint.sh
#
# Needs the local Jenkins up (compose.jenkins.yaml). Catches syntax and
# structure errors before a commit reaches the job.
set -euo pipefail
cd "$(dirname "$0")/../.."
URL=http://127.0.0.1:8091
auth="admin:$(cat ci/jenkins/.secrets/admin-password)"
jar="$(mktemp)"
trap 'rm -f "$jar"' EXIT
crumb=$(curl -fsS -u "$auth" -c "$jar" "$URL/crumbIssuer/api/json" \
  | python3 -c "import sys, json; d = json.load(sys.stdin); print(d['crumbRequestField'] + ':' + d['crumb'])")
result=$(curl -fsS -u "$auth" -b "$jar" -H "$crumb" -X POST -F "jenkinsfile=<Jenkinsfile" \
  "$URL/pipeline-model-converter/validate")
echo "$result"
grep -q "successfully validated" <<< "$result"
