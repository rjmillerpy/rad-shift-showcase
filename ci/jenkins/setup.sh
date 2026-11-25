#!/usr/bin/env bash
# Make the local Jenkins's secrets once (roadmap item 35), then start it:
#
#   ci/jenkins/setup.sh
#   docker compose -f compose.jenkins.yaml up -d --build
#   open http://localhost:8091      # user admin, password in ci/jenkins/.secrets/admin-password
#
# Everything goes in ci/jenkins/.secrets/ (gitignored, mode 700): never in
# ~/.ssh, never in Git. Rerunning keeps what exists, except the kind
# kubeconfig, which is refreshed (the cluster may have been recreated).
set -euo pipefail
cd "$(dirname "$0")"
SECRETS=.secrets
mkdir -p "$SECRETS"
chmod 700 "$SECRETS"

if [ ! -f "$SECRETS/admin-password" ]; then
  # No trailing newline: JCasC's readFile keeps it, and it would be part of the password.
  (umask 077 && openssl rand -hex 16 | tr -d "\n" > "$SECRETS/admin-password")
fi

# The controller's key for the agent: a key pair for this alone.
if [ ! -f "$SECRETS/agent-key" ]; then
  ssh-keygen -q -t ed25519 -N "" -C "jenkins-controller@radshift-local" -f "$SECRETS/agent-key"
fi
# The agent image authorizes the key it's given in this variable.
(umask 077 && echo "JENKINS_AGENT_SSH_PUBKEY=$(cat "$SECRETS/agent-key.pub")" > "$SECRETS/agent.env")

# The deploy stage's cluster, as seen from the kind network (--internal).
if kind get clusters 2>/dev/null | grep -qx rad-shift; then
  (umask 077 && kind get kubeconfig --name rad-shift --internal > "$SECRETS/kind-kubeconfig")
else
  echo "No kind cluster (scripts/kind_cluster.sh up): the deploy stage will fail until there is one." >&2
  (umask 077 && : > "$SECRETS/kind-kubeconfig")
fi
echo "Secrets ready in ci/jenkins/$SECRETS"
