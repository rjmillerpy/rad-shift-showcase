#!/usr/bin/env bash
# Run the playbook against a fresh local target, twice (roadmap item 38):
#
#   ansible/test.sh          # up, provision, provision again (must change nothing), check
#   ansible/test.sh down     # remove the target and its Docker data
#
# The target is a privileged systemd container standing in for a VPS
# (target/Dockerfile). Its engine's storage is on volumes: overlayfs can't
# stack on the container's own overlay root (Docker 29 keeps images in
# containerd, so both /var/lib/docker and /var/lib/containerd). Needs docker, ansible-core and the image the app role
# ships (radshift-backend:local, from scripts/kind_cluster.sh's build).
set -euo pipefail
cd "$(dirname "$0")"
NAME=radshift-ansible-target
IMAGE=radshift-ansible-target:local
SECRETS=.secrets
# The vault's password, for every ansible command below (not in ansible.cfg:
# there it would be required even to lint, where there is no password).
export ANSIBLE_VAULT_PASSWORD_FILE="$SECRETS/vault-password"

down() { docker rm -f -v "$NAME" >/dev/null 2>&1 || true; docker volume rm -f "$NAME-docker" "$NAME-containerd" >/dev/null; }
if [ "${1:-}" = down ]; then down; exit 0; fi

# Secrets, once: the provisioning key and the vault password (no newline).
mkdir -p "$SECRETS" && chmod 700 "$SECRETS"
[ -f "$SECRETS/ansible-key" ] || ssh-keygen -q -t ed25519 -N "" -C "ansible@radshift-local" -f "$SECRETS/ansible-key"
[ -f "$SECRETS/vault-password" ] || (umask 077 && openssl rand -hex 24 | tr -d "\n" > "$SECRETS/vault-password")
vault=inventories/local/group_vars/app_servers/vault.yml
if [ ! -f "$vault" ]; then
  (umask 077 && printf 'vault_db_password: %s\nvault_jwt_secret: %s\n' "$(openssl rand -hex 24)" "$(openssl rand -hex 32)" > "$vault")
  ansible-vault encrypt "$vault"
fi

echo "== target"
down
docker build -q -t "$IMAGE" target > /dev/null
docker run -d --name "$NAME" --hostname app1 --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run --tmpfs /run/lock \
  -v "$NAME-docker:/var/lib/docker" \
  -v "$NAME-containerd:/var/lib/containerd" \
  -v "$PWD/$SECRETS/ansible-key.pub:/home/ansible/.ssh/authorized_keys:ro" \
  -p 127.0.0.1:2222:22 "$IMAGE" > /dev/null
for _ in $(seq 30); do ssh-keyscan -p 2222 -t ed25519 127.0.0.1 > "$SECRETS/known_hosts.new" 2>/dev/null && [ -s "$SECRETS/known_hosts.new" ] && break; sleep 1; done
# A new target has a new host key: trust it on first use, as with a new VPS.
mv "$SECRETS/known_hosts.new" "$SECRETS/known_hosts"

ansible-galaxy collection install -r requirements.yml -p collections > /dev/null

echo "== first run"
ansible-playbook site.yml
echo "== second run: must change nothing"
ansible-playbook site.yml | tee "$SECRETS/second-run.log"
if ! grep -qE "app1 +: ok=[0-9]+ +changed=0 " "$SECRETS/second-run.log"; then
  echo "Not idempotent: the second run changed something." >&2
  exit 1
fi
# The API listens on the server's loopback only (a reverse proxy with TLS
# would front it on a real server), so check from there, over SSH as deploy.
echo "== on the server, as the deploy user"
ssh -i "$SECRETS/ansible-key" -o UserKnownHostsFile="$SECRETS/known_hosts" -p 2222 ansible@127.0.0.1 \
  'curl -fsS http://127.0.0.1:5000/health && echo && sudo -u deploy docker compose -f /opt/radshift/compose.yaml ps --format "{{.Service}} {{.Status}}"'
echo "== root login and passwords are refused"
# Captured first: under pipefail, `ssh | grep` fails on ssh's own (expected) exit code.
refusal=$(ssh -o BatchMode=yes -o UserKnownHostsFile="$SECRETS/known_hosts" -o PreferredAuthentications=password \
  -p 2222 root@127.0.0.1 true 2>&1 || true)
if ! grep -q "Permission denied (publickey)" <<< "$refusal"; then
  echo "SSH hardening not in effect: $refusal" >&2
  exit 1
fi
echo "refused: $refusal"
echo "Provisioned, deployed, idempotent."
