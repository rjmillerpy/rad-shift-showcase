# The local dev stack's AWS identity (item 9): an IAM user whose only
# permission is four S3 actions on objects in the media bucket. At go-live
# the same policy becomes the ECS task role's (infra/iam.tf).
#
# Its access key is NOT managed here: Terraform would store the secret in
# its state. Create and rotate it with the CLI (README.md).

data "aws_iam_policy_document" "app_media" {
  statement {
    sid = "MediaObjectsInOneBucket"
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:GetObject",
      "s3:AbortMultipartUpload",
    ]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/*"]
  }
}

resource "aws_iam_policy" "app_media" {
  name        = "radshift-app-media"
  description = "rad-shift API: upload and read media objects in ${var.media_bucket_name} only"
  policy      = data.aws_iam_policy_document.app_media.json
  tags        = { project = "rad-shift" }
}

resource "aws_iam_user" "app" {
  # checkov:skip=CKV_AWS_273: a laptop's docker stack can't assume a role without some long-lived credential; this one can touch 4 S3 actions on one bucket. ECS uses a task role instead
  name = "radshift-app"
  tags = { project = "rad-shift", purpose = "local-dev-app-credentials" }
}

resource "aws_iam_user_policy_attachment" "app_media" {
  # checkov:skip=CKV_AWS_40: one machine user with one policy; a group would only add indirection
  user       = aws_iam_user.app.name
  policy_arn = aws_iam_policy.app_media.arn
}

import {
  to = aws_iam_policy.app_media
  id = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/radshift-app-media"
}

import {
  to = aws_iam_user.app
  id = "radshift-app"
}

import {
  to = aws_iam_user_policy_attachment.app_media
  id = "radshift-app/arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/radshift-app-media"
}
