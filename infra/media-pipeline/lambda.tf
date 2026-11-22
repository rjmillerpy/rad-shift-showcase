# Item 27: web-sized WebP variants of every new post image
# (lambdas/image_variants/). S3 notifies the uploads queue (queue.tf) for
# each object created under posts/ with an image suffix, and since item 29 a
# Step Functions workflow (step_functions.tf) calls the function once per
# image; it writes under variants/ and returns the result.
#
# Cost, inside the always-free allowance at this app's volume: Lambda
# includes 1M requests and 400,000 GB-seconds a month; one image takes about
# 1.5 GB x 2 s = 3 GB-s, so that's 130,000 images. Logs: a few KB per image
# against CloudWatch's 5 GB.

data "aws_s3_bucket" "media" {
  bucket = var.media_bucket_name
}

locals {
  function_name            = "${var.project}-image-variants"
  function_timeout_seconds = 60
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "image_variants" {
  name               = local.function_name
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

# Least privilege: read only the trigger prefix, write only the output
# prefix, log only to its own group. It can't overwrite an upload.
data "aws_iam_policy_document" "image_variants" {
  statement {
    sid       = "ReadUploads"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.media.arn}/${var.source_prefix}*"]
  }
  statement {
    sid       = "WriteVariants"
    actions   = ["s3:PutObject", "s3:PutObjectAcl"]
    resources = ["${data.aws_s3_bucket.media.arn}/${var.variant_prefix}*"]
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.image_variants.arn}:*"]
  }
}

resource "aws_iam_role_policy" "image_variants" {
  name   = "image-variants"
  role   = aws_iam_role.image_variants.id
  policy = data.aws_iam_policy_document.image_variants.json
}

resource "aws_cloudwatch_log_group" "image_variants" {
  # checkov:skip=CKV_AWS_158: CloudWatch encrypts logs at rest by default; a customer KMS key is $1/month
  # checkov:skip=CKV_AWS_338: debugging logs, kept 14 days on purpose (storage is billed)
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "image_variants" {
  # checkov:skip=CKV_AWS_117: reaches only S3 and CloudWatch over AWS's public endpoints; a VPC would need a NAT (~$30/month) or endpoints
  # checkov:skip=CKV_AWS_50: X-Ray tracing adds cost; the app's own traces are OpenTelemetry (item 26)
  # checkov:skip=CKV_AWS_116: a function DLQ only covers async invokes; the workflow invokes it synchronously and parks failures itself (step_functions.tf)
  # checkov:skip=CKV_AWS_115: new accounts have a 10-concurrent-execution limit, all of it unreserved by rule; S3 invokes are bounded by uploads
  # checkov:skip=CKV_AWS_272: code signing needs AWS Signer profiles; the zip comes from this repository's own build
  # checkov:skip=CKV_AWS_173: no environment variables, so nothing to encrypt
  function_name    = local.function_name
  role             = aws_iam_role.image_variants.arn
  runtime          = "python3.12"
  architectures    = ["arm64"] # Graviton: about 20% cheaper per GB-second than x86
  handler          = "lambdas.image_variants.handler.handler"
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)
  # A 50 MB photo decodes to a few hundred MB of pixels; memory also buys CPU.
  memory_size = 1536
  timeout     = local.function_timeout_seconds

  depends_on = [aws_cloudwatch_log_group.image_variants, aws_iam_role_policy.image_variants]
}

data "aws_caller_identity" "current" {}

# The bucket's whole notification configuration: Terraform owns it from here
# (it had none). One rule per suffix, all under the trigger prefix, all to
# the uploads queue.
resource "aws_s3_bucket_notification" "media" {
  bucket = data.aws_s3_bucket.media.id

  dynamic "queue" {
    for_each = var.image_suffixes
    content {
      queue_arn     = aws_sqs_queue.uploads.arn
      events        = ["s3:ObjectCreated:*"]
      filter_prefix = var.source_prefix
      filter_suffix = queue.value
    }
  }

  # S3 sends a test message and checks it can deliver when this is saved.
  depends_on = [aws_sqs_queue_policy.uploads]
}
