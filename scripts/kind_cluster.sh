#!/usr/bin/env bash
# rad-shift on a local Kubernetes cluster (roadmap item 30). Free: kind runs
# the cluster as a Docker container on this machine; nothing uses EKS or AWS.
# See deploy/README.md.
#
#   scripts/kind_cluster.sh up       # cluster + ingress + metrics, build and load images, helm install
#   scripts/kind_cluster.sh gitops   # install Argo CD and hand the release to it (after `up`)
#   scripts/kind_cluster.sh down     # delete the cluster and everything in it
#
# Needs docker, kind, kubectl and helm on PATH (deploy/README.md pins them),
# and the frontend checkout beside this one (../rad-shift-frontend/my-social-feed).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT/../rad-shift-frontend/my-social-feed"
CLUSTER=rad-shift
CONTEXT="kind-$CLUSTER"
NAMESPACE=rad-shift
RELEASE=rad-shift
SECRET=rad-shift            # the chart's secretName
IMAGE_TAG=local             # the chart's image tags (values.yaml)
API_URL=http://api.rad-shift.localhost:8088   # baked into the frontend image

# Chart versions, each at least 14 days old when pinned.
TRAEFIK_CHART=42.3.1
METRICS_SERVER_CHART=3.14.0
ARGOCD_CHART=10.17.1

kc() { kubectl --context "$CONTEXT" "$@"; }

cluster_exists() { kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; }

create_cluster() {
  if cluster_exists; then
    echo "Cluster $CLUSTER exists"
  else
    kind create cluster --config "$ROOT/deploy/kind/cluster.yaml"
  fi
}

install_addons() {
  helm --kube-context "$CONTEXT" upgrade --install traefik traefik \
    --repo https://traefik.github.io/charts --version "$TRAEFIK_CHART" \
    --namespace traefik --create-namespace \
    --values "$ROOT/deploy/kind/traefik-values.yaml" --wait
  helm --kube-context "$CONTEXT" upgrade --install metrics-server metrics-server \
    --repo https://kubernetes-sigs.github.io/metrics-server/ --version "$METRICS_SERVER_CHART" \
    --namespace kube-system \
    --values "$ROOT/deploy/kind/metrics-server-values.yaml" --wait
}

# kind nodes can't pull from this machine's Docker, so the images are
# copied in. The API image skips the scraping browsers (~1 GB smaller).
build_and_load_images() {
  docker build --build-arg INSTALL_BROWSERS=false -t "radshift-backend:$IMAGE_TAG" "$ROOT"
  docker build --build-arg NEXT_PUBLIC_API_URL="$API_URL" -t "radshift-frontend:$IMAGE_TAG" "$FRONTEND_DIR"
  kind load docker-image --name "$CLUSTER" "radshift-backend:$IMAGE_TAG" "radshift-frontend:$IMAGE_TAG"
}

# Random values, made once and kept: the database volume holds the password
# it was created with. Never in Git, never printed.
create_secret() {
  kc create namespace "$NAMESPACE" --dry-run=client -o yaml | kc apply -f -
  if kc -n "$NAMESPACE" get secret "$SECRET" >/dev/null 2>&1; then
    echo "Secret $SECRET exists"
    return
  fi
  kc -n "$NAMESPACE" create secret generic "$SECRET" \
    --from-literal=DB_PASSWORD="$(openssl rand -hex 24)" \
    --from-literal=JWT_SECRET="$(openssl rand -hex 32)"
}

deploy_chart() {
  helm --kube-context "$CONTEXT" upgrade --install "$RELEASE" "$ROOT/deploy/helm/rad-shift" \
    --namespace "$NAMESPACE" --wait --timeout 10m
  # Same tag, new image: Kubernetes sees no change, so restart to pick it up.
  # (A real cluster deploys immutable tags, the commit SHA, and needs no restart.)
  kc -n "$NAMESPACE" rollout restart deployment
  kc -n "$NAMESPACE" rollout status deployment --timeout 5m
}

# Argo CD takes over the release: from here on, Git is what's deployed.
install_gitops() {
  helm --kube-context "$CONTEXT" upgrade --install argocd argo-cd \
    --repo https://argoproj.github.io/argo-helm --version "$ARGOCD_CHART" \
    --namespace argocd --create-namespace \
    --values "$ROOT/deploy/argocd/values.yaml" --wait
  # Forget Helm's record of the release (not its resources): Argo CD renders
  # the chart itself and would otherwise share ownership with `helm upgrade`.
  kc -n "$NAMESPACE" delete secret -l "owner=helm,name=$RELEASE" --ignore-not-found
  kc apply -f "$ROOT/deploy/argocd/application.yaml"
  echo "Argo CD UI: kubectl --context $CONTEXT -n argocd port-forward svc/argocd-server 8089:80"
  echo "  then http://localhost:8089, user admin, password from:"
  echo "  kubectl --context $CONTEXT -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}

case "${1:-}" in
  up)
    create_cluster
    install_addons
    build_and_load_images
    create_secret
    deploy_chart
    echo "rad-shift: http://rad-shift.localhost:8088 (API: $API_URL)"
    ;;
  gitops)
    cluster_exists || { echo "No cluster: run '$0 up' first" >&2; exit 1; }
    install_gitops
    ;;
  down)
    kind delete cluster --name "$CLUSTER"
    ;;
  *)
    echo "usage: $0 up|gitops|down" >&2
    exit 2
    ;;
esac
