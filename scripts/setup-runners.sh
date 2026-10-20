#!/usr/bin/env bash
# Self-hosted GitHub Actions runners for item 17's CD: one per repository
# (a personal account can't share runners between repositories), each a
# systemd *user* service, so no sudo. See DEPLOY.md.
#
#   scripts/setup-runners.sh            # download, verify, register, start
#   scripts/setup-runners.sh --remove   # stop, unregister, delete
#
# Needs gh logged in as the repositories' owner, plus docker, the AWS CLI and
# python3 for the jobs themselves.
#
# What this gives the jobs: they run as you, with Docker access (which is
# root-equivalent) and your home directory. Acceptable because both
# repositories are private and only you can push to them; never attach a
# self-hosted runner to a public repository, where a pull request from a
# fork could run code on your machine.
set -euo pipefail

VERSION=2.338.0
# From the release notes of v2.338.0 (BEGIN SHA linux-x64). Bump both together.
SHA256=af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32
OWNER=rjmillerpy
REPOS=(rad-shift rad-shift-frontend)
LABEL=radshift-local   # what the publish and deploy workflows ask for
DEPLOYING_REPO=rad-shift
RUNNERS_DIR="$HOME/actions-runner"
UNIT_DIR="$HOME/.config/systemd/user"
BACKEND_ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"

unit_name() { echo "actions-runner-$1.service"; }

download() {
  local tarball="$1"
  # HTTPS only, including any redirect (GitHub redirects release downloads).
  curl -fsSL --proto '=https' --tlsv1.2 -o "$tarball" \
    "https://github.com/actions/runner/releases/download/v$VERSION/actions-runner-linux-x64-$VERSION.tar.gz"
  echo "$SHA256  $tarball" | sha256sum --check --quiet
}

write_unit() {
  local repo="$1"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/$(unit_name "$repo")" <<EOF
[Unit]
Description=GitHub Actions runner for $OWNER/$repo (rad-shift item 17)
After=network-online.target

[Service]
WorkingDirectory=%h/actions-runner/$repo
# The runner's own service entrypoint, not run.sh: it puts the PATH that
# config.sh saved in .path in force (systemd's PATH lacks nvm's Node, so
# jobs would get the system's older node), and turns SIGTERM into the
# SIGINT the runner stops cleanly on.
ExecStart=%h/actions-runner/$repo/bin/runsvc.sh
Restart=on-failure
RestartSec=10
TimeoutStopSec=60

[Install]
WantedBy=default.target
EOF
}

install() {
  [[ -f "$BACKEND_ENV_FILE" ]] || { echo "No $BACKEND_ENV_FILE: the deploy needs the backend's .env" >&2; exit 1; }
  # Global, not local: the EXIT trap runs after this function has returned.
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  download "$tmp/runner.tar.gz"
  for repo in "${REPOS[@]}"; do
    local dir="$RUNNERS_DIR/$repo"
    mkdir -p "$dir"
    tar -xzf "$tmp/runner.tar.gz" -C "$dir"
    local token
    token="$(gh api -X POST "repos/$OWNER/$repo/actions/runners/registration-token" -q .token)"
    (cd "$dir" && ./config.sh --unattended --replace --url "https://github.com/$OWNER/$repo" \
      --token "$token" --name "$(hostname)-$repo" --labels "$LABEL" --work _work)
    write_unit "$repo"
  done
  # The runner reads its own .env into every job's environment.
  echo "RADSHIFT_ENV_FILE=$BACKEND_ENV_FILE" >> "$RUNNERS_DIR/$DEPLOYING_REPO/.env"
  systemctl --user daemon-reload
  for repo in "${REPOS[@]}"; do systemctl --user enable --now "$(unit_name "$repo")"; done
  echo "Runners started. They run while you're logged in; to keep them running"
  echo "after logout too: loginctl enable-linger \"$USER\""
}

remove() {
  for repo in "${REPOS[@]}"; do
    systemctl --user disable --now "$(unit_name "$repo")" 2> /dev/null || true
    rm -f "$UNIT_DIR/$(unit_name "$repo")"
    if [[ -x "$RUNNERS_DIR/$repo/config.sh" ]]; then
      local token
      token="$(gh api -X POST "repos/$OWNER/$repo/actions/runners/remove-token" -q .token)"
      (cd "$RUNNERS_DIR/$repo" && ./config.sh remove --token "$token")
    fi
    rm -rf "${RUNNERS_DIR:?}/$repo"
  done
  systemctl --user daemon-reload
  echo "Runners stopped, unregistered and deleted."
}

case "${1:-}" in
  "") install ;;
  --remove) remove ;;
  *) echo "usage: $0 [--remove]" >&2; exit 2 ;;
esac
