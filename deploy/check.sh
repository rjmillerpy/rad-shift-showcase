#!/usr/bin/env bash
# Check the Helm chart offline (roadmap item 30): lint it, validate every
# rendering against the Kubernetes API schemas, and run its tests.
#
#   deploy/check.sh
#
# Downloads the pinned helm and kubeconform (checksums verified) into a
# temporary directory, so the versions here are the ones checked. CI runs
# it in the kubernetes job; it needs no cluster.
set -euo pipefail
cd "$(dirname "$0")/.."

HELM_VERSION=v3.22.1
KUBECONFORM_VERSION=v0.8.0
# The cluster's version (deploy/kind/cluster.yaml): the schemas to check against.
KUBERNETES_VERSION=1.36.4
CHART=deploy/helm/rad-shift

TOOLS="$(mktemp -d)"
trap 'rm -rf "${TOOLS:?}"' EXIT
(
  cd "$TOOLS"
  curl -fsSLO "https://get.helm.sh/helm-$HELM_VERSION-linux-amd64.tar.gz"
  echo "$(curl -fsSL "https://get.helm.sh/helm-$HELM_VERSION-linux-amd64.tar.gz.sha256sum" | awk '{print $1}')  helm-$HELM_VERSION-linux-amd64.tar.gz" \
    | sha256sum -c --quiet
  tar xzf "helm-$HELM_VERSION-linux-amd64.tar.gz" --strip-components=1 linux-amd64/helm
  base="https://github.com/yannh/kubeconform/releases/download/$KUBECONFORM_VERSION"
  curl -fsSLO "$base/kubeconform-linux-amd64.tar.gz"
  curl -fsSL "$base/CHECKSUMS" | grep ' kubeconform-linux-amd64.tar.gz$' | sha256sum -c --quiet
  tar xzf kubeconform-linux-amd64.tar.gz kubeconform
)
export PATH="$TOOLS:$PATH"

echo "== helm lint"
helm lint --strict "$CHART"

# The defaults plus every switch the tests flip, each validated as rendered.
echo "== Kubernetes $KUBERNETES_VERSION schemas"
for settings in "" \
    "--set backend.autoscaling.enabled=false" \
    "--set worker.enabled=false" \
    "--set kafka.enabled=false" \
    "--set postgres.enabled=false --set postgres.host=db.example.internal"; do
  echo "-- ${settings:-defaults}"
  # shellcheck disable=SC2086 # word splitting is the point
  helm template rad-shift "$CHART" $settings \
    | kubeconform -strict -summary -kubernetes-version "$KUBERNETES_VERSION"
done
# The Argo CD Application is a custom resource with no built-in schema:
# checked for well-formed YAML by its tests instead.

echo "== Chart tests"
pytest -q -m helm tests/deploy
