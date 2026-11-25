#!/usr/bin/env bash
# The deploy job's KUBECONFIG, as a gitlab-ci-local file variable (roadmap
# item 37). On GitLab it would be a masked, protected project variable;
# here it is ci/gitlab/variables.yml, gitignored and mode 600.
#
#   ci/gitlab/setup.sh          # after scripts/kind_cluster.sh up
set -euo pipefail
cd "$(dirname "$0")"
kubeconfig="$(kind get kubeconfig --name rad-shift --internal)"  # as seen on the kind network
(
  umask 077
  {
    echo "KUBECONFIG:"
    echo "  type: file"
    echo "  values:"
    echo "    \"*\": |"
    sed 's/^/      /' <<< "$kubeconfig"
  } > variables.yml
)
echo "ci/gitlab/variables.yml ready"
