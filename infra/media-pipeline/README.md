# Media pipeline (roadmap Phase 5)

Background work on uploaded media, on real AWS. Unlike the main stack (`../`),
which waits for go-live, this one is applied now: at rad-shift's volume
everything here fits AWS's always-free monthly allowances.

## Item 27: image variants (Lambda)

When the API stores a post image (`posts/…` with a `.jpg/.jpeg/.png/.webp`
suffix), S3 queues a notification and `radshift-image-variants` reads it
(item 28, below)
(`lambdas/image_variants/`), which writes a WebP per width under
`variants/`: `posts/a_1_0.jpg` → `variants/posts/a_1_0-480.webp` and
`-1280.webp`, never upscaled, public and cacheable for a year. The original
is never touched.

| Resource | What it is |
|---|---|
| `aws_lambda_function.image_variants` | Python 3.12 on arm64 (Graviton), 1,536 MB, 60 s timeout. Zip from `scripts/build_lambda.py`. |
| `aws_iam_role.image_variants` + policy | Read `posts/*`, write `variants/*`, log to its own group. Nothing else. |
| `aws_cloudwatch_log_group.image_variants` | `/aws/lambda/radshift-image-variants`, 14 days. |
| `aws_s3_bucket_notification.media` | **Owns the bucket's whole notification configuration** (it had none). Since item 28 it targets the uploads queue. |

The safety rule: the function writes under a different prefix from the one
that triggers it. Writing under `posts/` would trigger it again for every
output, forever, billed per invocation. A variable validation refuses
overlapping prefixes, and `tests/lambdas/` checks the code and this stack
agree.

## Item 28: queues, dead letters and results (SQS + SNS)

```
S3 posts/*.jpg ─notify─► radshift-media-uploads ─batches of 5─► image-variants Lambda ─► radshift-media-results ─poll─► API
                              │ 3 failed receives                                                  (app/media/ records
                              ▼                                                                     sizes on the post)
                         radshift-media-uploads-dlq ─CloudWatch alarm─► radshift-media-alerts (SNS) ─► email
```

| Resource | Why |
|---|---|
| `aws_sqs_queue.uploads` | Decouples uploads from processing: a burst waits instead of hitting the account's 10 concurrent executions. Visibility timeout 6 × the function's 60 s, as AWS advises. |
| `aws_lambda_event_source_mapping.uploads` | Batches of 5, `ReportBatchItemFailures` (only the failed message is retried), at most 2 concurrent invocations. |
| `aws_sqs_queue.uploads_dlq` | After 3 failed receives a message is parked here for 14 days instead of being lost. |
| `aws_cloudwatch_metric_alarm.uploads_dead_letters` + SNS topic | Emails when anything lands in the dead-letter queue (and again when it's empty). The address is `alert_email` in `media.auto.tfvars` (gitignored); confirm AWS's subscription email first. |
| `aws_sqs_queue.results` | The Lambda reports `{bucket, source_key, width, variants}` here. AWS can't reach a database on a laptop, so the API polls (`MEDIA_RESULTS_QUEUE_URL`), records the sizes on the post (`posts.image_variants`), and the frontend builds a `srcset`. 14 days' retention covers the laptop being off. |
| `aws_iam_policy.app_results` | The API's user may receive and delete results, nothing else. |

A broken image is logged and skipped, not retried (a retry can't fix it).
After fixing a real failure, move the parked messages back:
`aws sqs start-message-move-task --source-arn <dead-letter queue ARN> --profile radshift-admin`.

Delivery is at least once, so both ends are idempotent: a retried
message rewrites the same variant objects and records the same URLs.

## Deploy

```sh
uv run python scripts/build_lambda.py                 # dist/image_variants.zip
cd infra/media-pipeline
AWS_PROFILE=radshift-admin terraform init -backend-config=backend.hcl
AWS_PROFILE=radshift-admin terraform plan -out=media.tfplan
AWS_PROFILE=radshift-admin terraform apply media.tfplan
```

The zip is reproducible, so a rebuild with no code change gives the same
hash and Terraform leaves the function alone.

Watch it: `aws logs tail /aws/lambda/radshift-image-variants --follow --profile radshift-admin`.

## Cost

| | Free every month | One image | Free images/month |
|---|---|---|---|
| SQS requests | 1M | ~6 (send, receive, delete, result) | idle pollers use most: Lambda's ~650k/month worst case + the API's ~130k |
| SNS email | 1,000 | 0 (failures only) | — |
| CloudWatch alarms | 10 | — | this stack uses 1 |
| Lambda requests | 1M | 1 per batch | 1M |
| Lambda compute | 400,000 GB-s | ~1.5 GB × 2 s = 3 GB-s | ~130,000 |
| CloudWatch Logs | 5 GB | a few KB | millions |
| S3 | — | 2 small WebPs stored, 1 GET + 2 PUTs | ~$0.00001 each |

Expected bill: $0.00, plus fractions of a cent for S3 requests. The
$5 and $20 budget alerts (`../account/`) still apply.

Tests: `terraform test` here (offline, mock provider) and
`uv run pytest tests/lambdas tests/scripts/test_build_lambda.py`.
