# Jenkins: the same pipeline, the enterprise way

Roadmap item 35. A local Jenkins builds rad-shift from the `Jenkinsfile` in the repository
root. It's free: two containers on this machine. Everything is configuration as code, with no
click-through setup.

```sh
ci/jenkins/setup.sh                                    # secrets, once (into ci/jenkins/.secrets/, gitignored)
docker compose -f compose.jenkins.yaml up -d --build   # http://localhost:8091, admin / .secrets/admin-password
ci/jenkins/lint.sh                                     # validate the Jenkinsfile with Jenkins's own linter
docker compose -f compose.jenkins.yaml down            # stop (add -v to drop build history and caches)
```

The job builds what's **committed on `main`** in this checkout, which is mounted read-only at
`/repo`. It polls every 2 minutes; in a real setup a webhook would trigger it instead. The
deploy stage needs the kind cluster (`scripts/kind_cluster.sh up`), and you need to rerun
`setup.sh` after recreating the cluster.

| File | What it is |
|---|---|
| `../../Jenkinsfile` | The pipeline |
| `Dockerfile.controller` | Jenkins 2.580.2 LTS (by digest), plus the plugin lockfile and `casc.yaml` |
| `Dockerfile.agent` | `jenkins/ssh-agent` 9.4.0 (by digest), plus uv, helm and kubectl, each checksum-verified |
| `casc.yaml` | Configuration as Code: the admin user, 0 executors on the controller, the SSH agent, credentials, and the job (Job DSL) |
| `plugins.txt` | A lockfile: all 83 plugins pinned, not just the 10 used directly |
| `setup.sh`, `lint.sh` | Secrets; Jenkinsfile validation |

## The pipeline

Build (`uv sync --locked`) → Lint (ruff ‖ mypy) → Test → Scan (bandit ‖ pip-audit) → Package →
Deploy to staging.

- **Test:** pytest with JUnit XML and Cobertura coverage, which Jenkins records as the test
  trend and coverage report.
- **Package:** `helm package` gives the chart a version (`0.1.0-build.N`) and stamps it with
  the commit. It's archived with a fingerprint, so Jenkins can show which builds used it.
- **Deploy to staging:**
  - It waits for a person to approve.
  - It then installs **that packaged chart**, unstashed from the Package stage rather than
    re-checked-out: what was tested is what ships.
  - The target is `rad-shift-staging` on kind: one API pod, no Kafka, no ingress, and its own
    random Secret.
  - It finishes with a smoke test (`/health` from inside the pod).
- **`agent none` at the top:** each stage asks for an agent, so the approval wait holds no
  executor. Checked during the drill: the agent showed `idle: true` while the build waited.

## Controller vs agents

- **The controller** schedules, stores history, and serves the UI and credentials. It has
  **0 executors**: a build running on the controller can read Jenkins's own files, every
  stored secret included.
- **The agent** runs the steps. The controller connects to it over SSH:
  - It uses a key made for this alone, stored in `.secrets/`, never `~/.ssh`.
  - The agent's host key is trusted on first use and refused if it changes.
  - The alternative is inbound agents, where the agent connects to the controller (JNLP or
    WebSocket). Cloud setups launch an ephemeral agent per build (Kubernetes or EC2 plugins).
- **Credentials:** the agent's key and the kind kubeconfig are Jenkins credentials, loaded by
  JCasC from files mounted at `/run/secrets`. The pipeline uses them only through
  `withCredentials`, which also masks them in the log.

## Drills (2026-11-25)

- **Green run:** a full build in about 3 minutes (tests: 3,338 passed in 100 s), approved, then
  deployed to staging in 27 s, with the smoke test returning `{"status":"ok"}`.
- **Red run:** a deliberately failing test (a local commit, then reverted). The build failed at
  Test with `1 failed, 3338 passed`, the JUnit report showed `failCount: 1`, and Scan, Package
  and Deploy were skipped.

### What broke along the way (failure stories)

1. **Plugin dependency hell.**
   - `jenkins-plugin-cli --latest false` picked the minimum dependency versions, and the set
     didn't fit: `credentials-binding` needed a newer `plain-credentials`, so the whole Pipeline
     suite failed to load.
   - The default resolution, on the other hand, pulled 9 plugins younger than the 14-day
     supply-chain cooldown.
   - The fix was a real lockfile:
     1. Resolve once.
     2. Check each version's release date.
     3. Pin the too-new ones one release back.
     4. Commit all 83.
   - My first lockfile also silently dropped the 10 top-level plugins, because the resolver
     lists dependencies separately. JCasC then did nothing, with no error. A test now requires
     them.
2. **The admin password didn't work:** JCasC's `${readFile:...}` keeps the trailing newline,
   so the real password ended in `\n`. `setup.sh` now writes the file without one.
3. **"Unable to find Jenkinsfile":** the lightweight checkout didn't accept the `*/main` branch
   spec against a `file://` remote; `main` works.
4. **`uvx: not found`:** the agent image only extracted `uv`. Now it uses `uv tool run`, the
   same command.
5. **"Bad substitution":** `sh` steps run `/bin/sh` (dash here), which has no bash
   `${VAR:0:12}`.

## Updating plugins

1. Change a top-level version in `plugins.txt`.
2. Resolve: `docker run --rm -v "$PWD/ci/jenkins/plugins.txt:/p.txt:ro" --entrypoint jenkins-plugin-cli radshift-jenkins-controller --plugin-file /p.txt --no-download --list`.
3. Re-pin the "Resulting plugin list", holding back anything under 14 days old.
4. Rebuild, then start with a fresh `jenkins-home` volume. Jenkins copies plugins from the
   image only on first start.

## Interview points

- **Jenkins vs GitHub Actions:**
  - Jenkins: self-hosted, plugins, Groovy, and you run it.
  - Actions: hosted, YAML, a marketplace.
  - Enterprises keep Jenkins for on-prem, air-gapped or legacy reasons.
- **Pipeline syntax:**
  - Declarative vs scripted pipelines.
  - `agent none` with per-stage agents.
  - Parallel stages, `post` conditions, `input`, `stash` vs `archiveArtifacts`, fingerprints.
- **Running Jenkins safely:**
  - Configuration as Code and Job DSL, instead of hand-configured controllers ("snowflake
    Jenkins").
  - Plugin sprawl and pinning as the main operational risk.
  - Credentials scoping and masking.
  - Why controllers should not build.
  - Shared libraries for reuse across repositories.
  - Multibranch pipelines with webhooks, instead of polling.
