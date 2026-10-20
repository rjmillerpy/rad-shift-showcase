# Account setup as code (roadmap item 16)

Item 9 built these by hand (console and CLI). This stack describes them and
adopts them with `import` blocks, so they are reviewed, tested and
reproducible like everything else. All free.

| Resource | What it is |
|---|---|
| `aws_budgets_budget.monthly` | `radshift-monthly-5` and `radshift-monthly-20`: email at 80% and 100% of actual spend and when the month's forecast passes 100% |
| `aws_iam_policy.app_media`, `aws_iam_user.app` | The local stack's identity: 4 S3 object actions on `radshift-bucket/*`, nothing else |
| `aws_ssoadmin_permission_set.admin` + assignment | The `radshift-admin` SSO profile: AdministratorAccess in 4-hour sessions for one Identity Center user |

**Not here on purpose:** the app user's access key (Terraform would keep the
secret in its state; rotate it with `aws iam create-access-key` /
`delete-access-key`), the root user (its key is deactivated; password and MFA
only), the media bucket (predates this; adopt it the same way at go-live).

## Plan and apply

`budget_alert_email` is a variable so the address stays out of the repo. Put
it in `account.auto.tfvars` (gitignored, mode 600):

```sh
cd infra/account
echo 'budget_alert_email = "you@example.com"' > account.auto.tfvars && chmod 600 account.auto.tfvars
AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl
AWS_PROFILE=radshift-admin terraform plan -out=account.tfplan
# Plan: 8 to import, 0 to add, 5 to change, 0 to destroy.
AWS_PROFILE=radshift-admin terraform apply account.tfplan
```

The 5 changes are the `managed_by = "terraform"` tag being added, which marks
what is now under Terraform; the first plan also showed the code missing a
`project` tag on the permission set (applying would have deleted it), which is
the point of reading an import plan before applying. After the apply, the
`import` blocks are history: they stay as a record and do nothing on later
runs.

Tests: `terraform test` (4 offline runs; mock providers can't import, so each
imported resource has an `override_resource` stand-in).
