# Continuous delivery (roadmap item 17)

Every commit on `main` that passes CI becomes an image in ECR, tagged with
its commit SHA, and the newest images are deployed to the compose stack on
your machine, health-gated, with automatic rollback. The pipeline costs
about 5-10 cents a month (ECR storage) and no Actions minutes: its jobs run
on a self-hosted runner on your machine.

```
rad-shift main ──CI ok──▶ Publish (backend image) ──▶ Deploy (newest backend + frontend)
                                       │                     │
rad-shift-frontend main ──CI ok──▶ Publish (frontend image)  └─▶ local `radshift` stack
                                       │
                                       ▼
                         ECR: radshift-backend:<sha>, radshift-frontend:<sha>
```

| Piece | Where |
|---|---|
| Registry: two ECR repositories, immutable tags, the 10 newest kept | `infra/registry/` |
| One OIDC role per repository: each pushes only its own image; the backend's also pulls both, to deploy | `infra/github-oidc/`, `infra/registry/ci_access.tf` |
| Build and push, skipped if the SHA is already in ECR | `.github/workflows/publish.yml` here and in rad-shift-frontend |
| Deploy: pull, start, wait for health checks, check from the host, roll back on failure | `.github/workflows/deploy.yml`, `scripts/deploy.py`, `compose.deploy.yaml` |
| Runners: one per repository, systemd user services | `scripts/setup-runners.sh` |

## One-time setup

1. Apply the roles, then the registry (`AWS_PROFILE=radshift-admin`):

   ```sh
   aws sso login --profile radshift-admin
   cd infra/github-oidc && terraform init -backend-config=backend.hcl
   terraform plan -out=oidc.tfplan        # 1 to add (frontend role), the backend role moved, not replaced
   terraform apply oidc.tfplan
   cd ../registry && terraform init -backend-config=backend.hcl
   terraform plan -out=registry.tfplan    # 6 to add
   terraform apply registry.tfplan
   ```

2. Point each repository at its role (an ARN is not a secret: it grants
   nothing without a matching OIDC token):

   ```sh
   cd ../github-oidc
   gh variable set AWS_DEPLOY_ROLE_ARN --repo rjmillerpy/rad-shift-frontend \
     --body "$(terraform output -json deploy_role_arns | jq -r .frontend)"
   ```

   (The backend repository's variable is already set, from item 13.)

3. Install the runners: `scripts/setup-runners.sh`. It downloads the runner,
   checks its SHA-256, registers one runner per repository with the label
   `radshift-local`, and starts them as `systemctl --user` services.
   `scripts/setup-runners.sh --remove` undoes all of it.

## Using it

- **Normal flow:** merge to `main`. After CI passes, Publish builds and
  pushes, then Deploy runs the newest images of both components.
- **A frontend change:** its publish only pushes the image. Run Deploy
  (Actions → Deploy → Run workflow, or `gh workflow run deploy.yml`) to put it live,
  or let the next backend deploy take it along.
- **Roll back, or pin a version:** Run workflow with `backend_tag` and/or
  `frontend_tag` set to a commit SHA that is still in ECR:
  `gh workflow run deploy.yml -f backend_tag=<sha>`.
- **While CI can't run** (Actions minutes used up until 2026-11-01): run
  Publish by hand in each repository (`gh workflow run publish.yml`), then Deploy.
  Manual Publish skips the CI gate, so it is the break-glass path, not the normal one.
- **What's deployed?** `docker compose -p radshift ps` shows the image of
  each service; the Deploy run's summary lists them too.

## What a deploy checks

1. Each tag is a commit SHA (it comes from a form; anything else is
   rejected) and is still in ECR.
2. The new images are pulled before anything stops, so a registry problem
   leaves the running stack alone.
3. `docker compose up --wait` returns only when every health check passes:
   Postgres accepts connections, the API's `/health` reaches the database,
   the frontend answers `/api/health`.
4. Both services answer 200 from the host, and each runs the expected image.
5. Any failure: the previous images start again, and the run fails, saying
   whether the rollback worked.

Migrations run when the backend starts (`docker-entrypoint.sh`), and a
rollback doesn't undo them. Schema changes have to work with the previous
image too: add the new column or table, deploy, and remove what only the old
code needed in a later release (expand, then contract).

## Security

- **No AWS keys anywhere.** Each job gets an hour of credentials through
  OIDC, for its repository's role only, and only on `main`.
- **The runner runs jobs as you,** with Docker access, which is
  root-equivalent. Acceptable here because both repositories are private and
  only you can push to them. Never attach a self-hosted runner to a public
  repository: a pull request from a fork could run code on your machine.
- **Actions are pinned to commit SHAs** in these workflows (tags elsewhere):
  they run on your machine, and a tag can be moved to malicious code.
- **Docker login is per job** (`DOCKER_CONFIG` under the job's temp
  directory), so the ECR token never lands in your `~/.docker`.
- **Inputs go through `env`,** never straight into a `run:` script, so a
  `$(...)` typed into the form can't execute.
- **No GitHub environments:** a job that names one gets a different OIDC
  `sub` (`repo:<owner>/<name>:environment:<name>`), which the roles don't
  trust, and required reviewers on private repositories need a paid plan.
  The manual Run workflow button is the approval gate for now.

## Limits of the $0 version

- The frontend image has its API URL baked in at build time (Next.js
  `NEXT_PUBLIC_*`), so one image can't serve two environments. The images
  target the plain local stack (`http://localhost:5000`), not the TLS overlay.
  At go-live, set the frontend repository's `NEXT_PUBLIC_API_URL` variable to
  `https://<api_hostname>`.
- One environment. A real setup deploys to staging automatically and
  promotes the same image to production behind an approval.
- Jobs queue while your machine is off (and fail after 24 hours).

## At go-live

The Deploy job's last step becomes `aws ecs update-service --force-new-deployment`
with a new task definition revision naming the image tag (`infra/deploy_role.tf`
already grants exactly that), on a GitHub-hosted runner. ECS then does what
`scripts/deploy.py` does here: it starts the new tasks, waits for the load
balancer's health checks, and its deployment circuit breaker rolls back a
deploy that never gets healthy.
