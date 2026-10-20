#!/usr/bin/env bash
# Static checks for every Terraform stack in infra/ (roadmap item 16):
#
#   infra/lint.sh
#
# tflint runs twice: with the defaults ($0 mode) and in go-live mode (RDS
# and a domain). Resources behind `count = 0` are skipped by tflint, so a
# bad RDS instance class would pass the default run unseen.
# Checkov then scans for insecure settings; deliberate exceptions are
# inline `checkov:skip` comments with the reason.
#
# Needs tflint (pinned in .github/workflows/ci.yml) and uv.
set -euo pipefail
cd "$(dirname "$0")"

config="$PWD/.tflint.hcl"
tflint --init --config="$config" > /dev/null

echo "== tflint, default mode (all stacks)"
tflint --recursive --config="$config" --format compact
echo "== tflint, go-live mode (RDS + domain)"
tflint --config="$config" --format compact \
  --var database_mode=rds --var domain_name=example.com --var api_hostname=api.example.com

echo "== checkov"
# --no-build: wheels only, so installing the tools runs no package's build script.
uv run --project tools --locked --no-build --quiet checkov --directory . --framework terraform \
  --skip-path tools --compact --quiet

echo "All infra checks passed."
