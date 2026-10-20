# Container registry (roadmap item 17)

The two ECR repositories that CD pushes to, and what each repository's CI
role may do with them. Applied now: it is what the local deploy pulls from
today, and what ECS will pull from at go-live. The main stack (`../`) only
looks the repositories up by name, so destroying the app never deletes the
images you would roll back to.

| Resource | What it is |
|---|---|
| `aws_ecr_repository.app["backend"]`, `["frontend"]` | `radshift-backend`, `radshift-frontend`. Immutable tags (each tag is a commit SHA and always means the same image), scan on push (free), `force_delete = false`. |
| `aws_ecr_lifecycle_policy.app` | Keeps the 10 newest images per repository (`images_kept`, at least 2 so a rollback target exists). |
| `aws_iam_role_policy.ci["backend"]` | On `radshift-github-deploy`: push the backend image; pull both images, because the deploy workflow lives in the backend repository. |
| `aws_iam_role_policy.ci["frontend"]` | On `radshift-frontend-github-deploy`: push the frontend image. Nothing else. |

The roles (and who may assume them) are in `../github-oidc/`. Apply that
stack first: these policies attach to roles that must already exist.

## Cost

Storage is $0.10/GB-month. Versions share their base layers, so ten of each
image stay well under 1 GB: about 5-10 cents a month. Pushing is free;
pulling to your machine counts as internet egress, inside AWS's 100 GB/month
free allowance, and a deploy only downloads the layers that changed. Basic
scanning is free.

## Apply (one-off)

```sh
cd infra/registry
AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl
AWS_PROFILE=radshift-admin terraform plan -out=registry.tfplan   # expect: 6 to add
AWS_PROFILE=radshift-admin terraform apply registry.tfplan
```

## Tests

`terraform test` (mock provider, offline):
- immutable tags, scan on push, no `force_delete`, the names the main stack expects;
- the lifecycle keeps 10 images, and keeping fewer than 2 is rejected;
- each role pushes only its own repository; the frontend role can't reach the backend repository at all;
- only the deploying repository pulls every image, and pulling never comes with pushing;
- `Resource "*"` only for `ecr:GetAuthorizationToken`, no wildcard actions.

Mutation-checked: pushing to every repository, letting every role pull,
granting push in the pull statement, and a second `Resource "*"` action
each fail a test, as does a mutable tag.
