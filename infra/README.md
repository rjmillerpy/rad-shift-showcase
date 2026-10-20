# infra/ — AWS deployment as Terraform (roadmap items 10–16)

ECS Fargate behind an Application Load Balancer, with images in ECR.
**Written in $0 mode:** validated, tested offline and planned against the real
account, but never applied. Nothing here exists in AWS until the app goes live.

```
              internet
                 │  :443 (with domain_name; :80 redirects), else :80
         ┌───────▼────────┐  Host: api.<domain> ──► backend target group
         │  ALB (2 AZs)   │  anything else       ──► frontend target group
         └───┬────────┬───┘
   public subnet A   public subnet B        (no NAT gateway)
     ┌──────▼──┐    ┌──▼───────┐
     │ backend │    │ frontend │   Fargate (Spot) tasks, public IP,
     │ :5000   │    │ :3000    │   reachable only from the ALB's security group
     └────┬────┘    └──────────┘
          ├─► S3 media bucket   (task role: 4 actions on one bucket)
          ├─► SSM parameters    (secrets, injected by ECS at start)
          └─► Postgres          database_mode: "external" (Neon, $0) or "rds" (private subnets)
```

## Commands (from `infra/`)

```bash
aws sso login --profile radshift-admin           # the state is in S3, so init needs credentials
AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl   # once: provider + S3 state
terraform fmt -recursive                         # format
terraform validate                               # syntax and references
terraform test                                   # 35 offline tests
./lint.sh                                        # tflint (default + go-live mode) and Checkov (item 16), mock provider, no credentials
AWS_PROFILE=radshift-admin terraform plan -var-file=example.tfvars   # reads the account, creates nothing (40 to add)
AWS_PROFILE=radshift-admin terraform plan -var-file=example.tfvars -var database_mode=rds -var db_host=   # with RDS (46 to add)
```

Never run `terraform apply` here until go-live (the separate, free `github-oidc/` stack is the exception) (see [the cost rule](#cost)).
CI runs fmt, validate and test on every push (`terraform` job in `.github/workflows/ci.yml`).

## Design decisions (and what each test pins)

| Decision | Why | Test |
|---|---|---|
| Backend `desired_count = 1`, deploys stop the old task first (`max 100% / min 0%`) | Every API process starts the generator scheduler; two tasks would scrape twice. Costs a short outage per deploy until the scheduler is its own service. | `backend_never_runs_two_tasks`, `rejects_a_second_backend_task` |
| Frontend deploys start the new task first (`200% / 100%`) | Stateless, so no outage | `frontend_deploys_without_downtime` |
| Secrets from SSM Parameter Store, never plain env | No secret in Terraform, its state, or the task definition | `secrets_come_from_ssm_never_plain_env` |
| Execution role vs task role | ECS pulls images, writes logs and reads secrets with the execution role; the app's code only gets the task role (4 S3 actions on one bucket) | `backend_task_role_is_least_privilege`, `task_roles_trust_only_this_account` |
| Public subnets, no NAT gateway | A NAT gateway is ~$36/month; tasks take a public IP and the security group only admits the ALB | `internet_route_uses_the_free_gateway_not_nat`, `tasks_only_reachable_from_the_load_balancer` |
| Images in `registry/`, looked up here by name | The repositories are applied now (item 17) and outlive any cluster; a destroy here can't take the rollback targets along | `tasks_run_images_from_the_registry_stack` |
| Log retention 14 days, Container Insights off, Fargate Spot | Cost guards | `cost_guards` |
| Host-based routing | Backend and frontend share one ALB | `api_host_routes_to_the_backend` |
| Two alarms to SNS email: target 5xx over 5% for 5 min, unhealthy backend for 5 min | The go-live twins of the local Prometheus rules (item 15), on the ALB's free metrics. No traffic doesn't page; no health data does | `alarms_page_through_sns`, `error_rate_alarm_matches_the_prometheus_rule`, `unhealthy_backend_alarm_treats_silence_as_down`, `alert_email_subscribes_when_set` |
| `METRICS_ENABLED=false` on ECS | Nothing scrapes the app on AWS; a route that doesn't exist can't be reached by a path trick an ALB rule might miss (case, `%6D` encoding) | `metrics_endpoint_is_off_on_aws` |
| `us-east-2` | The existing media bucket is there; same prices as us-east-1, no cross-region transfer | — |
| Widget server execution forced off | The executor is not a sandbox | `widget_execution_stays_off` |
| Database swappable by one variable: `external` (Neon free plan, $0) or `rds` | Going live is a variable change, not a rewrite | `external_mode_creates_no_database`, `external_mode_requires_a_host` |
| RDS: private subnets, no public access, only the tasks' security group on 5432, TLS forced | The database is never on the internet | `rds_is_private_encrypted_and_backed_up`, `rds_only_reachable_from_the_tasks` |
| RDS generates and keeps the password (`manage_master_user_password`); ECS injects its `password` key | The password is never in code, plans or state | `rds_password_never_in_terraform` |
| Deletion protection, final snapshot, 7-day backups, encrypted gp3 with autoscaling to 50 GB | A `destroy` can't lose the data | `rds_is_private_encrypted_and_backed_up` |
| `domain_name` switches on HTTPS (`dns.tf`): ACM certificate with DNS validation, Route 53 alias records, an HTTPS listener with TLS 1.3/1.2 only, and port 80 reduced to a 301 redirect | Empty by default, so the plan stays $0; going live is one variable. DNS validation renews without a person | `https.tftest.hcl` (7 runs), `http_only_without_a_domain` |
| Validation records keyed by the configured host names, not by ACM's answer | ACM's validation options are only known after the certificate is requested, and `for_each` keys must be known at plan time | `certificate_covers_both_hosts_and_validates_by_dns` |
| The VPC's default security group is managed with no rules | Anything placed in it by mistake gets no traffic | `default_security_group_allows_nothing` |
| `protect_from_deletion` (default on) covers the ALB and RDS | A stray `terraform destroy` can't take the site down; off only for throwaway practice stacks | `load_balancer_protected_from_deletion` |
| RDS: IAM database authentication on, Postgres logs to a log group created first with 14-day retention | People log in with short-lived tokens; RDS's own log group would keep logs forever | `rds_logs_expire_and_iam_login_is_available` |

The app side of item 11 (`app/common/db.py`): `pool_pre_ping`, `pool_recycle` and a
connect timeout, because managed Postgres drops connections (RDS restarts and
failovers, Neon suspending when idle). `e2e/test_resilience.py` restarts the
database under the running stack and requires the next request to succeed; it
fails without `pool_pre_ping`.

The tests were mutation-checked: breaking the deploy settings, adding a fifth
S3 action, or passing a secret as plain env each fails the suite.

## Stacks

| Directory | What | Applied? |
|---|---|---|
| `infra/` | The app: VPC, ALB, ECS, database, DNS, alarms | No, plan only until go-live ($0) |
| `github-oidc/` | GitHub Actions' keyless AWS roles, one per repository (items 13, 17) | Yes ($0) |
| `registry/` | The two ECR repositories and what each CI role may push or pull (item 17) | Applied by you (pennies) |
| `account/` | Budgets, the app's IAM user and policy, the admin permission set (item 9), adopted with `import` blocks | Applied by you ($0; changes only tags) |
| `state-backend/` | The S3 bucket every stack's state moves into | Applied by you (pennies) |

Real plans, 2026-10-16: `infra/` default 45 to add; with RDS 52; `account/`
8 to import, 0 to add, 0 to destroy.

## Static checks (item 16)

`infra/lint.sh` runs in CI (the `terraform` job) and as a pre-commit hook on
`.tf` changes:

- **tflint** (pinned in `ci.yml`; AWS ruleset pinned in `.tflint.hcl`) with
  every core rule on, run twice: with the defaults, and in go-live mode
  (`database_mode=rds`, a `domain_name`). tflint skips resources behind
  `count = 0`, so an invalid RDS instance class passed the default run;
  the second run catches it.
- **Checkov** (locked in `tools/`, apart from the app, because it pins an old
  boto3). 186 checks pass. The 28 exceptions are `checkov:skip` comments on
  the resource, each with its reason. Most are cost decisions (customer KMS
  keys at $1/month, WAF, Multi-AZ, flow logs, Container Insights, one-year
  log retention); the rest are design (TLS ends at the ALB, public task IPs
  instead of a NAT gateway, and the HTTPS redirect, which sits behind a
  condition Checkov can't follow). One worth knowing for interviews:
  CloudWatch alarms can't publish to an SNS topic encrypted with the
  AWS-managed key, so "encrypt the topic" needs a paid customer key.
- Trivy (`trivy config`) is the usual alternative. It was passed over
  because its release binaries, Docker images and GitHub Action tags were
  hijacked in March 2026 (CVE-2026-33634); if you use it, pin by digest.

## Cost

Today: the ECR repositories in `registry/` (about 5-10 cents a month for
ten images of each) and the state bucket (pennies). At go-live (us-east-2, 24/7,
prices checked 2026-10-07; confirm on the AWS pricing pages):

| | ~ $/month |
|---|---|
| Backend task, 1 vCPU / 2 GB (on-demand; Spot ~70% less) | 36 |
| Frontend task, 0.25 vCPU / 0.5 GB | 9 |
| ALB + 2 public IPv4 | 23 |
| 2 task public IPv4 | 7 |
| CloudWatch logs | < 1 |
| Database: Neon free plan (`external`) | 0 |
| Database: RDS db.t4g.micro + 20 GB gp3 + managed secret (`rds`) | ~14 |

## Going live (in order)

1. Item 16: state in S3 (`state-backend/`; see its README for the migration).
2. Item 12: load the secrets: `python scripts/sync_ssm_secrets.py --apply --env-file .env.production --profile radshift-admin`, then `--check` shows all present.
3. Item 11: pick the database. Neon: create the project, set `db_host`, store its password as `/radshift/DB_PASSWORD`. RDS: set `database_mode = "rds"` (nothing else; the password is created and injected automatically). Then restore data with `pg_dump` / `pg_restore`; the entrypoint runs migrations on start.
4. Item 14: buy the domain (this creates its Route 53 hosted zone, $0.50/month), then set `domain_name` and `api_hostname` (inside that domain). `dns.tf` requests and validates the certificate and adds the records, and the HTTP listener starts redirecting.
5. Set the frontend repository's `NEXT_PUBLIC_API_URL` variable to `https://<api_hostname>` (baked in at build time) and publish both images (item 17's publish workflows), then set the image tags.
6. Item 17b, feature flags: until flagd runs on ECS, `FLAGD_HOST` is unset there and every flag serves its fallback (off: no widget execution, and Chronicle narrates by rules, not Claude). To use the flags, add flagd as a sidecar container in the backend task, syncing `flags/flags.flagd.json` from S3 or an HTTPS URL, and set `FLAGD_HOST=localhost` (see `flags/README.md`).
7. `terraform apply` with a real tfvars file (`*.auto.tfvars` is gitignored).
   This also attaches `deploy_role.tf` to `radshift-github-deploy` (created by item 13 in `github-oidc/`, applied before go-live): `ecs:UpdateService` on the two services (image push and pull come from `registry/`), and `iam:PassRole` for the three task roles, only to ECS.
