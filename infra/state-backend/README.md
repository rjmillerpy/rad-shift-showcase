# Terraform state bucket (roadmap item 16)

One S3 bucket holds the state of every other stack (`infra/`,
`infra/github-oidc/`, later `infra/account/`), each under its own key.
Cost: pennies (state files are kilobytes).

| Setting | Why |
|---|---|
| Name `radshift-tfstate-<account id>` | Bucket names are global across all AWS accounts |
| Versioning, old versions kept 90 days | Every apply leaves a restore point for a broken or emptied state file |
| SSE-S3 encryption, all public access blocked, ACLs off | State can contain secrets (generated passwords, private keys) |
| Bucket policy denies non-TLS requests | No state in plain text on the wire |
| `prevent_destroy` | Losing the bucket loses track of every managed resource |
| Locking: S3-native (`use_lockfile = true` in each backend) | Terraform 1.10+ locks with a lock object next to the state. The older way, a DynamoDB table, still comes up in interviews; it's deprecated and no longer needed |

This stack's own state stays local (`terraform.tfstate`, gitignored): the
bucket can't hold the state of the stack that creates it. If that file is
lost, `terraform import aws_s3_bucket.state radshift-tfstate-<account id>`
(and the same for the bucket's other settings) restores it.

## Apply (one-off)

```sh
cd infra/state-backend
terraform init
AWS_PROFILE=radshift-admin terraform plan -out=state.tfplan   # 7 to add
AWS_PROFILE=radshift-admin terraform apply state.tfplan
```

## Move a stack's state into it

Done 2026-10-16 for `github-oidc/` and `account/` (`infra/` had no state
yet; it starts in S3). Each stack has a `backend "s3"` block whose settings
live in its `backend.hcl`. `-migrate-state` copies the local state up and
asks before switching:

```sh
cd infra/github-oidc
AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl -migrate-state
AWS_PROFILE=radshift-admin terraform plan    # must say "No changes"
```

Only after the plan shows no changes, delete the local `terraform.tfstate`
and its `.backup`: S3 holds the state and its versions now.

Locking, checked: with one plan running, `terraform.tfstate.tflock` appears
next to the state, and a second plan fails with "Error acquiring the state
lock" until the first finishes.

Tests: `terraform test` (4 offline runs on a mock provider).
