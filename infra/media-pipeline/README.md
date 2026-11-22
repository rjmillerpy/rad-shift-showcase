# Media pipeline (roadmap Phase 5)

Background work on uploaded media, on real AWS. Unlike the main stack (`../`),
which waits for go-live, this one is applied now: at rad-shift's volume
everything here fits AWS's always-free monthly allowances.

## Item 27: image variants (Lambda)

When the API stores a post image (`posts/…` with a `.jpg/.jpeg/.png/.webp`
suffix), S3 queues a notification and the media workflow calls
`radshift-image-variants` for it (items 28 and 29, below)
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
S3 posts/*.jpg ─notify─► radshift-media-uploads ─Pipe─► radshift-media workflow ─► radshift-media-results ─poll─► API
                              │                          (item 29, below)            (app/media/ records sizes on the post)
                              ▼ failures, after retries
                         radshift-media-uploads-dlq ─CloudWatch alarm─► radshift-media-alerts (SNS) ─► email
```

| Resource | Why |
|---|---|
| `aws_sqs_queue.uploads` | Decouples uploads from processing: a burst waits in the queue instead of being dropped. |
| `aws_sqs_queue.uploads_dlq` | Failures are parked here for 14 days instead of being lost: by the workflow after its retries, or by SQS after 3 receives if the Pipe can't start the workflow. |
| `aws_cloudwatch_metric_alarm.uploads_dead_letters` + SNS topic | Emails when anything lands in the dead-letter queue (and again when it's empty). The address is `alert_email` in `media.auto.tfvars` (gitignored); confirm AWS's subscription email first. |
| `aws_sqs_queue.results` | The workflow reports `{bucket, source_key, width, variants}` here. AWS can't reach a database on a laptop, so the API polls (`MEDIA_RESULTS_QUEUE_URL`), records the sizes on the post (`posts.image_variants`), and the frontend builds a `srcset`. 14 days' retention covers the laptop being off. |
| `aws_iam_policy.app_results` | The API's user may receive and delete results, nothing else. |

A broken image is logged and skipped, not retried (a retry can't fix it).
A parked message is the original S3 notification, with the error, the key
and the workflow execution as message attributes. After fixing the cause,
move them back to the uploads queue to replay them:
`aws sqs start-message-move-task --source-arn <dead-letter queue ARN> --profile radshift-admin`.

Item 28 first had the Lambda read the queue itself (batches of 5, partial
batch failures). Item 29 moved retries, reporting and failure handling into
the workflow, so the function only resizes.

## Item 29: the media workflow (Step Functions)

`state_machine.asl.json`, started for each queued notification by an
EventBridge Pipe (`aws_pipes_pipe.uploads`, batch size 1, fire and forget):

```
EachMessage (Map) → IsTestEvent? → EachImage (Map)
                                     MakeVariants ── Lambda, Retry: throttling ×4 (backoff 2×, jitter), errors ×2 (backoff 3×)
                                     ├─ AnyVariants? ── yes → ReportResult (sqs:sendMessage, results queue)
                                     │                  no  → NothingToReport (not an image, too small, unreadable)
                                     └─ Catch → ParkInDeadLetterQueue (sqs:sendMessage + error attributes) → Failed
```

- **Standard, not Express:** Standard has a free tier (4,000 state
  transitions a month) and keeps every execution's history for 90 days,
  which is where you debug a failed image. Express has neither, and is for
  high-volume, short work.
- **Service integrations instead of code:** reporting and parking are
  `sqs:sendMessage` states, not boto3 calls in the Lambda.
- **Logs:** failures only (`ERROR`), without execution data, to
  `/aws/vendedlogs/states/radshift-media` for 14 days.
- `tests/lambdas/test_state_machine.py` checks the definition against the
  Lambda and the API (keys, the variants field, every task's Catch), and AWS's
  `validate-state-machine-definition` accepts it.

Watch an upload: Step Functions console → `radshift-media` → the newest
execution shows each state's input and output.


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
| SQS requests | 1M | ~5 (send, receive, delete, result) | idle polling uses most: the Pipe's and the API's (~130k/month) long polls |
| SNS email | 1,000 | 0 (failures only) | — |
| CloudWatch alarms | 10 | — | this stack uses 1 |
| Step Functions (Standard) | 4,000 transitions | ~6 | ~650, then ~$0.00015 an image |
| EventBridge Pipes | none | 1 event | $0.40 per million: ~$0.0000004 an image |
| Lambda requests | 1M | 1 | 1M |
| Lambda compute | 400,000 GB-s | ~1.5 GB × 2 s = 3 GB-s | ~130,000 |
| CloudWatch Logs | 5 GB | a few KB | millions |
| S3 | — | 2 small WebPs stored, 1 GET + 2 PUTs | ~$0.00001 each |

Expected bill: $0.00 below ~650 images a month, plus fractions of a cent
for S3 requests and the Pipe. The $5 and $20 budget alerts (`../account/`)
still apply.

Tests: `terraform test` here (offline, mock provider) and
`uv run pytest tests/lambdas tests/scripts/test_build_lambda.py`.
