# rad-shift on Kubernetes

Roadmap item 30. The whole app runs on a local [kind](https://kind.sigs.k8s.io/) cluster,
deployed by a Helm chart and kept in sync with Git by Argo CD. It costs nothing: kind runs
Kubernetes inside a Docker container on this machine. An EKS control plane alone would be
about $73 a month, so nothing here uses EKS.

| Path | What it is |
|---|---|
| `helm/rad-shift/` | The chart: API, frontend, scheduler worker, Kafka aggregator, Postgres, Kafka, Ingress, HPA, PDB |
| `kind/cluster.yaml` | The cluster: one node, `localhost:8088` mapped to the ingress controller |
| `kind/traefik-values.yaml`, `kind/metrics-server-values.yaml` | The add-ons: ingress controller, and CPU metrics for the HPA |
| `argocd/` | Argo CD's settings and the `Application` that points it at the chart |
| `check.sh` | Offline checks: `helm lint`, kubeconform against the 1.36 schemas, the chart tests (CI's `kubernetes` job) |
| `../scripts/kind_cluster.sh` | `up`, `gitops`, `down` |

## Tools

Install these into `~/.local/bin` and verify each against its published checksum. Each release
was at least 14 days old when it was pinned.

| Tool | Version |
|---|---|
| kind | v0.33.0 (node image `kindest/node:v1.36.4`, pinned by digest) |
| kubectl | v1.36.6 |
| helm | v3.22.1 |
| kubeconform | v0.8.0 (`check.sh` downloads its own copy) |

## Run it

```sh
scripts/kind_cluster.sh up        # ~5 min the first time: cluster, add-ons, images, secret, helm install
open http://rad-shift.localhost:8088          # the site
curl http://api.rad-shift.localhost:8088/health   # the API
```

`*.localhost` always resolves to this machine. Both hosts share one port, and the ingress
routes on the `Host` header. The cluster can run alongside the Compose stack, which uses
3000, 5000 and 5433.

```sh
kubectl --context kind-rad-shift -n rad-shift get pods,hpa,ingress
scripts/kind_cluster.sh gitops    # install Argo CD and hand the release to it
scripts/kind_cluster.sh down      # delete the cluster and everything in it
```

The script makes a Secret called `rad-shift` once, with a random `DB_PASSWORD` and
`JWT_SECRET`. The chart only refers to it by name, so no secret is ever in Git. To give the
API its real keys, add them to that Secret (`kubectl edit secret rad-shift`) and restart the
Deployments. On a real cluster the Secret would come from AWS Secrets Manager through External
Secrets.

## What's in the chart, and why

- **API (`backend`)**:
  - Scaling: a Deployment scaled by an HPA (2–4 pods at 70% CPU). Its `replicas` field is left
    out on purpose; otherwise every upgrade or Argo CD sync would reset the HPA's count.
  - Probes:
    - readiness is `GET /health`, which runs `SELECT 1`;
    - liveness is `GET /health/live`, which only checks the process answers.

    If liveness checked the database too, a database outage would restart every pod and fix
    nothing.
  - Rollouts and drains:
    - `maxUnavailable: 0`, so no pod is lost during a rollout;
    - a 5 s `preStop` sleep, so in-flight requests finish while the endpoint list catches up;
    - a PDB keeps one pod up through a node drain.
- **Migrations**: every API pod runs `scripts/prepare_db.py` at start, under a PostgreSQL
  advisory lock. Pods started together take turns, and the first one migrates. Without the
  lock, two `create_all()` calls on an empty database collide.
- **Scheduler (`worker`)**: the API pods run with `GENERATOR_SCHEDULER_ENABLED=false`, and one
  worker pod runs the scheduler. With one scheduler per API pod, every due source would run
  once per replica. The worker uses `Recreate`, so a rollout never runs two at once.
- **Aggregator**: the Kafka consumer from item 29b. It can run up to one replica per partition.
- **Postgres and Kafka**: each is a StatefulSet with a volume, so the pod keeps its name and
  its data. `persistentVolumeClaimRetentionPolicy: Retain` means `helm uninstall` keeps the
  data. On AWS these would be RDS and either MSK or self-managed brokers
  (`postgres.enabled=false`, `postgres.host=...`).
- **Kafka's `enableServiceLinks: false`**: Kubernetes adds `KAFKA_PORT=tcp://...` for a Service
  called kafka, and the image reads every `KAFKA_*` variable as broker config.
- **Hardening**: every container:
  - runs as non-root, with seccomp `RuntimeDefault`;
  - has no privilege escalation and drops all capabilities;
  - has a read-only root filesystem, with writable `emptyDir`s only where needed;
  - has requests and a memory limit.

  The chart tests enforce all of this.
- **Config**: non-secret settings live in a ConfigMap. A checksum of it is in each pod
  template, so changing a setting rolls the pods.

## GitOps with Argo CD

`scripts/kind_cluster.sh gitops` does the following:

1. Installs Argo CD with Helm (chart 10.17.1, Argo CD v3.6.1, without Dex, notifications or
   ApplicationSets).
2. Deletes Helm's record of the release, leaving its resources in place.
3. Applies `argocd/application.yaml`.

From then on, Argo CD renders the chart from Git and applies it:

- **automated sync**: a push shows up within about a minute;
- **prune**: anything deleted from the chart is deleted from the cluster;
- **selfHeal**: any change made by hand with `kubectl` is put back.

The Application tracks the **public mirror** (`rad-shift-showcase`), which `open_core/publish.py`
updates on every push to `main`. That means no Git credential has to live in the cluster. A
private source would need a read-only deploy key stored as an Argo CD repository Secret.

To open the UI:

```sh
kubectl --context kind-rad-shift -n argocd port-forward svc/argocd-server 8089:80
kubectl --context kind-rad-shift -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d     # user: admin
```

## Shortcuts a laptop takes, and what a real cluster does instead

| Here | Real cluster |
|---|---|
| Images loaded with `kind load`, tag `local`, then a rollout restart | Images pushed to ECR with immutable commit-SHA tags; bumping the tag in Git triggers the rollout |
| One node, so no topology spread or pod anti-affinity | Spread the API across zones (`topologySpreadConstraints`) |
| Postgres and Kafka in the cluster | RDS, plus MSK or a Kafka operator (Strimzi) |
| A Secret made by the script | External Secrets syncing from AWS Secrets Manager |
| Plain HTTP on `localhost:8088` | TLS at the ingress or load balancer (cert-manager or ACM) |
| Traefik as a NodePort | A `LoadBalancer` Service: an AWS NLB, or ALB through the AWS Load Balancer Controller |
