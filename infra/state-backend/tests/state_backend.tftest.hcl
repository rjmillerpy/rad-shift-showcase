# Offline tests on a mock provider: no credentials, nothing created.
# Run: terraform test (from infra/state-backend/).

mock_provider "aws" {
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::radshift-tfstate-123456789012" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
}

run "bucket_name_is_unique_to_the_account" {
  assert {
    condition     = aws_s3_bucket.state.bucket == "radshift-tfstate-123456789012"
    error_message = "Bucket names are global: include the account id."
  }
}

run "every_write_keeps_a_restore_point" {
  assert {
    condition     = one(aws_s3_bucket_versioning.state.versioning_configuration).status == "Enabled"
    error_message = "Versioning lets a broken state file be rolled back."
  }
  assert {
    condition     = one(one(aws_s3_bucket_lifecycle_configuration.state.rule).noncurrent_version_expiration).noncurrent_days == 90
    error_message = "Old versions expire, or storage grows with every apply."
  }
}

run "never_public_and_encrypted" {
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "State can hold secrets: every public-access block on."
  }
  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "Encrypted at rest."
  }
  assert {
    condition     = one(aws_s3_bucket_ownership_controls.state.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs off: IAM and the bucket policy decide access."
  }
}

run "plain_http_is_refused" {
  assert {
    condition = anytrue([
      for s in data.aws_iam_policy_document.state.statement :
      s.effect == "Deny" && anytrue([for c in s.condition : c.variable == "aws:SecureTransport" && c.values == tolist(["false"])])
    ])
    error_message = "The bucket policy must deny any request not made over TLS."
  }
}
