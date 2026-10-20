#!/usr/bin/env bash
# Free stand-ins for commercial SAST/SCA (roadmap item 21), the same commands
# CI runs (.github/workflows/security.yml, publish.yml):
#
#   scripts/security-scan.sh                 # Semgrep + pip-audit
#   scripts/security-scan.sh --image IMAGE   # ...plus a Grype scan of IMAGE
#
# Needs docker (Semgrep runs in its pinned image), uv, and for --image grype
# on PATH (installed, checksum-verified: README.md "Security scanning").
set -euo pipefail
cd "$(dirname "$0")/.."

SEMGREP_IMAGE="semgrep/semgrep:1.179.0@sha256:93963d9295a366f59e4850127b1550400ee7b388f04fe144e4a1f6325d96e01b"
PIP_AUDIT="pip-audit==2.10.1"
# Semgrep's curated rules plus the language packs this repository uses.
SEMGREP_RULESETS=(p/default p/python p/typescript p/react)
# ecdsa in Checkov's tool environment: a timing side channel in ECDSA signing,
# no fix released (the maintainers treat side channels as out of scope).
# Checkov runs locally on our own Terraform and signs nothing.
TOOLS_IGNORED_VULNS=(PYSEC-2026-1325)

semgrep_scan() {
  echo "== Semgrep"
  local configs=()
  for ruleset in "${SEMGREP_RULESETS[@]}"; do configs+=(--config "$ruleset"); done
  # --metrics=off: nothing about the code is reported to semgrep.dev.
  docker run --rm -v "$PWD:/src:ro" "$SEMGREP_IMAGE" \
    semgrep scan --metrics=off --error --quiet "${configs[@]}" /src
}

pip_audit_project() {
  local project="$1"
  shift
  echo "== pip-audit ($project)"
  local requirements
  requirements="$(mktemp)"
  (cd "$project" && uv export --frozen --no-hashes --format requirements-txt --quiet) > "$requirements"
  uvx --quiet "$PIP_AUDIT" -r "$requirements" --no-deps --disable-pip --progress-spinner off "$@"
  rm -f "$requirements"
}

grype_scan() {
  echo "== Grype ($1)"
  # Fail only on critical CVEs that have a fix: something we can act on.
  grype "$1" --fail-on critical --only-fixed --config .grype.yaml
}

main() {
  semgrep_scan
  pip_audit_project .
  local ignores=()
  for id in "${TOOLS_IGNORED_VULNS[@]}"; do ignores+=(--ignore-vuln "$id"); done
  pip_audit_project infra/tools "${ignores[@]}"
  if [[ "${1:-}" == "--image" ]]; then grype_scan "$2"; fi
  echo "Security scans passed."
}

main "$@"
