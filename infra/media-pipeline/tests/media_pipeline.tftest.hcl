# Offline tests (mock AWS provider): what the function may touch, what
# triggers it, and that it can never trigger itself.
# Run: terraform test (from infra/media-pipeline/).

mock_provider "aws" {
  override_data {
    target = data.aws_s3_bucket.media
    values = {
      id  = "radshift-bucket"
      arn = "arn:aws:s3:::radshift-bucket"
    }
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  override_data {
    target = data.aws_iam_policy_document.lambda_trust
    values = { json = "{}" }
  }
}

variables {
  lambda_zip = "tests/fixtures/placeholder.zip"
}

run "the_function_is_small_cheap_and_bounded" {
  command = plan

  assert {
    condition     = aws_lambda_function.image_variants.architectures == tolist(["arm64"])
    error_message = "arm64 (Graviton) is the cheaper architecture."
  }
  assert {
    condition     = aws_lambda_function.image_variants.timeout <= 60
    error_message = "A stuck image must not bill for up to 15 minutes."
  }
  assert {
    condition     = aws_lambda_function.image_variants.handler == "lambdas.image_variants.handler.handler"
    error_message = "The handler path is the package's repository path (scripts/build_lambda.py)."
  }
  assert {
    condition     = aws_cloudwatch_log_group.image_variants.retention_in_days == 14
    error_message = "Logs expire; CloudWatch storage is billed forever otherwise."
  }
  assert {
    condition     = aws_cloudwatch_log_group.image_variants.name == "/aws/lambda/radshift-image-variants"
    error_message = "Lambda writes to /aws/lambda/<function>; any other group would be created by Lambda itself, with no retention."
  }
}

run "permissions_are_one_prefix_each" {
  command = plan

  assert {
    condition = (
      data.aws_iam_policy_document.image_variants.statement[0].resources
      == toset(["arn:aws:s3:::radshift-bucket/posts/*"])
    )
    error_message = "The function reads only uploads under posts/."
  }
  assert {
    condition = (
      data.aws_iam_policy_document.image_variants.statement[1].resources
      == toset(["arn:aws:s3:::radshift-bucket/variants/*"])
    )
    error_message = "The function writes only under variants/: it can never overwrite an upload."
  }
  assert {
    condition = (
      data.aws_iam_policy_document.image_variants.statement[0].actions == toset(["s3:GetObject"])
    )
    error_message = "Read-only on uploads: no delete, no list."
  }
}

run "only_post_images_trigger_it" {
  command = plan

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_notification.media.lambda_function :
      rule.filter_prefix == "posts/" && contains([".jpg", ".jpeg", ".png", ".webp"], rule.filter_suffix)
    ])
    error_message = "Only images under posts/ invoke the function (videos and documents would be wasted invocations)."
  }
  assert {
    condition     = length(aws_s3_bucket_notification.media.lambda_function) == 4
    error_message = "One rule per image suffix."
  }
  assert {
    condition     = aws_lambda_permission.s3_invoke.source_account == "123456789012"
    error_message = "Only this account's bucket may invoke it (a bucket name can be re-registered by anyone)."
  }
}

run "overlapping_prefixes_are_refused" {
  command = plan

  variables {
    variant_prefix = "posts/variants/"
  }

  expect_failures = [var.variant_prefix]
}
