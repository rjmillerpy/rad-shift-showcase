# Artifact repository: immutable versions, promotion, retention

Roadmap item 39. The roadmap's advice was to learn the idea, not the vendor: JFrog Artifactory's
free tier is limited, and ECR or GHCR teach the same thing for nothing. rad-shift's artifact
repository is **Amazon ECR** (`infra/registry/`, built in item 17), plus the Helm chart that the
pipelines version and promote. This page maps each idea to where it lives here.

## The ideas, and where they live

| Idea | In rad-shift |
|---|---|
| **One build, many deploys.** Build once; every environment runs that exact artifact, never a rebuild. | `publish.yml` builds each image once per commit. The Jenkins and GitLab pipelines package the chart once, then deploy *that file* (Jenkins `stash`/`unstash`, GitLab `needs: [package]`). |
| **Immutable versions.** A version always means the same bytes. | ECR repositories are `IMMUTABLE`, and each tag is the commit SHA. Pushing a tag again fails, so `publish.yml` checks first. A `terraform test` fails if the repository is made mutable. |
| **Traceability.** From a running thing back to its source. | Image tag = commit SHA; `SENTRY_RELEASE` = the same SHA (item 25). The chart is `0.1.0-build.N`/`-pipeline.N` with `appVersion` = the commit. Jenkins fingerprints the archived chart, so it can show which builds made and used it. |
| **Promotion between environments.** An artifact moves from one environment to the next after passing its checks there; it's never rebuilt. | Inside a pipeline: package, then staging (approval, then the smoke test). Into the cluster: Argo CD deploys what Git names (item 30), so promoting means changing Git, and rolling back is a `git revert`. |
| **Retention.** Keep enough to roll back; expire the rest. | The ECR lifecycle keeps the 10 newest images. A validation refuses fewer than 2, so there's always a rollback target. `force_delete = false`: destroying a repository that still holds images fails. |
| **Rollback.** Redeploy a previous version, quickly. | `scripts/deploy.py` health-gates every deploy and restarts the previous SHAs if it fails (drilled in item 17). Any SHA still in ECR can be deployed by hand. |
| **Scanning before use.** | ECR scan on push (free), plus Grype on the image in `publish.yml` with critical-and-fixable as the gate (item 21). |
| **Access control.** Who may push, who may pull. | Each repository's CI role can push only its own image; only the deploying repository can pull both, and pulling never comes with pushing (tested). |
| **A proxy for upstream packages.** Artifactory's other half: cache PyPI and npm, and block what's bad. | Approximated without a server: lockfiles (`uv.lock`, `package-lock.json`, the Jenkins plugin lockfile), a 14-day release cooldown (`exclude-newer`, `min-release-age`), digests on every base image, and checksums on every downloaded tool. |

## What's not done, and what it would take

All three are cheap (cents a month or less), but they need an ECR session
(`aws sso login --profile radshift-admin`), and two need a Terraform apply. Per the
pennies-until-live rule, they're written down rather than done.

1. **The chart as an OCI artifact in ECR.**
   - Today the chart lives in Git and in CI artifact stores.
   - Instead: `helm push dist/rad-shift-<version>.tgz oci://<registry>/radshift-charts`, into a
     third immutable repository with its own lifecycle. A chart is about 20 KB, so roughly $0.
   - Argo CD can track an OCI chart version instead of a Git path; then promotion means bumping
     a version number.
2. **Promote by digest, not tag.**
   - Deploys name `radshift-backend:<sha>`. Because tags are immutable, that tag already can't
     change.
   - Naming `@sha256:<digest>` makes the same guarantee hold without trusting the registry's
     setting. It's also what a signature (3) attaches to.
3. **Sign and attest.**
   - Sign each pushed image (Sigstore `cosign`), attach an SBOM (Syft) and provenance (SLSA).
   - Deploy only what verifies: an admission policy in Kubernetes, or a `cosign verify` in
     `deploy.py`.
   - That's the supply-chain step past scanning.

## Interview points

- **What an artifact repository does:** stores versioned build outputs (images, charts, wheels,
  jars, npm packages), proxies upstream registries, controls access, retains and expires
  versions, and supports promotion.
- **Mutable `latest` vs immutable SHA tags,** and why "it worked in staging" means something
  only when staging and production run the same digest.
- **Promotion models:**
  - separate repositories per environment, with a copy by digest;
  - promotion tags, where immutability forbids moving them;
  - GitOps, where an environment's file names the version.
- **Retention vs rollback depth,** and the fact that a lifecycle rule counts every image
  manifest: `publish.yml` pushes one plain manifest, not an index plus children, so it can't
  expire a child that a tagged index still needs.
- **Artifactory vs Nexus vs ECR/GHCR/Artifact Registry:**
  - Artifactory and Nexus: universal formats, upstream proxies, on-prem.
  - ECR, GHCR, Artifact Registry: cloud-native, mostly containers and OCI artifacts.
