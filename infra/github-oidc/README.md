# GitHub OIDC deploy role (roadmap item 13)

Lets GitHub Actions use AWS **without any stored AWS key**. This is the only
part of the AWS setup that is applied now: IAM is free, so it costs $0.

| Resource | What it is |
|---|---|
| `aws_iam_openid_connect_provider.github` | Tells AWS to trust tokens signed by `token.actions.githubusercontent.com` with audience `sts.amazonaws.com`. |
| `aws_iam_role.github_deploy["backend"]` (`radshift-github-deploy`) | The role the backend repository's workflows assume. The trust policy only accepts `repo:rjmillerpy/rad-shift:ref:refs/heads/main`, so it rejects pull requests, other branches, tags, forks and other repositories. |
| `aws_iam_role.github_deploy["frontend"]` (`radshift-frontend-github-deploy`) | The same for `rjmillerpy/rad-shift-frontend` (item 17). One role per repository, so a frontend workflow can't push a backend image. |

**No permissions in this stack.** `sts:GetCallerIdentity` needs none. Each
stack that owns resources grants access to exactly those: `../registry/`
(push and pull images, item 17) and, at go-live, the main stack
(`../deploy_role.tf`, ECS deploy).

Item 13 created the backend role as a single resource; item 17's `for_each`
gives it the key `"backend"`, and a `moved` block in `main.tf` tells
Terraform it is the same role, so the plan shows a move, not a
destroy-and-create.

## How it works

1. The `aws-identity` job in `.github/workflows/ci.yml` has
   `permissions: id-token: write`, so it can ask GitHub for an OIDC token.
   The token is a signed JWT whose claims include `sub`
   (`repo:<owner>/<name>:ref:refs/heads/<branch>`) and `aud`.
2. `aws-actions/configure-aws-credentials` sends the token to
   `sts:AssumeRoleWithWebIdentity`.
3. STS checks the signature against the OIDC provider and the claims against
   the trust policy, then returns credentials that expire within an hour.

## Apply (one-off)

```sh
cd infra/github-oidc
AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl
AWS_PROFILE=radshift-admin terraform plan -out=oidc.tfplan   # item 17: 1 to add (frontend role), 1 moved
AWS_PROFILE=radshift-admin terraform apply oidc.tfplan
gh variable set AWS_DEPLOY_ROLE_ARN --repo rjmillerpy/rad-shift \
  --body "$(terraform output -json deploy_role_arns | jq -r .backend)"
gh variable set AWS_DEPLOY_ROLE_ARN --repo rjmillerpy/rad-shift-frontend \
  --body "$(terraform output -json deploy_role_arns | jq -r .frontend)"
```

The ARN goes in a repository **variable**, not a secret: it grants nothing
without a token that matches the trust policy. Until it is set, the
`aws-identity` job skips.

## State

In S3 (`s3://radshift-tfstate-123456789012/github-oidc/terraform.tfstate`,
versioned, locked during each operation), moved there in item 16. Set up a
checkout with `AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl`. If the state were ever lost, import instead of
recreating:

```sh
terraform import aws_iam_openid_connect_provider.github \
  arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
terraform import 'aws_iam_role.github_deploy["backend"]' radshift-github-deploy
terraform import 'aws_iam_role.github_deploy["frontend"]' radshift-frontend-github-deploy
```

## Tests

`terraform test` (mock provider, offline) pins the trust policy:
- an exact `StringEquals` on `aud` and `sub`, with no `StringLike`;
- a single statement, with the OIDC provider as the only principal;
- one role per repository, each trusting only its own repository;
- a session length of one hour;
- wildcards in the repository or branch name are rejected.

Widening `sub` to `repo:rjmillerpy/rad-shift:*` fails two tests, as it should.
