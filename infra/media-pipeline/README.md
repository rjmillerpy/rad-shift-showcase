# Media pipeline (roadmap Phase 5)

Background work on uploaded media, on real AWS. Unlike the main stack (`../`),
which waits for go-live, this one is applied now: at rad-shift's volume
everything here fits AWS's always-free monthly allowances.

## Item 27: image variants (Lambda)

When the API stores a post image (`posts/…` with a `.jpg/.jpeg/.png/.webp`
suffix), S3 invokes `radshift-image-variants`
(`lambdas/image_variants/`), which writes a WebP per width under
`variants/`: `posts/a_1_0.jpg` → `variants/posts/a_1_0-480.webp` and
`-1280.webp`, never upscaled, public and cacheable for a year. The original
is never touched.

| Resource | What it is |
|---|---|
| `aws_lambda_function.image_variants` | Python 3.12 on arm64 (Graviton), 1,536 MB, 60 s timeout. Zip from `scripts/build_lambda.py`. |
| `aws_iam_role.image_variants` + policy | Read `posts/*`, write `variants/*`, log to its own group. Nothing else. |
| `aws_cloudwatch_log_group.image_variants` | `/aws/lambda/radshift-image-variants`, 14 days. |
| `aws_lambda_permission.s3_invoke` | Only the media bucket, in this account, may invoke it. |
| `aws_s3_bucket_notification.media` | **Owns the bucket's whole notification configuration** (it had none). |

The safety rule: the function writes under a different prefix from the one
that triggers it. Writing under `posts/` would trigger it again for every
output, forever, billed per invocation. A variable validation refuses
overlapping prefixes, and `tests/lambdas/` checks the code and this stack
agree.

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
| Lambda requests | 1M | 1 | 1M |
| Lambda compute | 400,000 GB-s | ~1.5 GB × 2 s = 3 GB-s | ~130,000 |
| CloudWatch Logs | 5 GB | a few KB | millions |
| S3 | — | 2 small WebPs stored, 1 GET + 2 PUTs | ~$0.00001 each |

Expected bill: $0.00, plus fractions of a cent for S3 requests. The
$5 and $20 budget alerts (`../account/`) still apply.

Tests: `terraform test` here (offline, mock provider) and
`uv run pytest tests/lambdas tests/scripts/test_build_lambda.py`.
