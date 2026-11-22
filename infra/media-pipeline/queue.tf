# Item 28: the uploads queue between S3 and the work, a dead-letter queue
# with an email alarm, and a results queue the API polls. Item 29 put a
# Step Functions workflow between the queues (step_functions.tf).
#
#   S3 posts/*.jpg ──notify──► uploads queue ──Pipe──► workflow (Lambda per image) ──► results queue ──poll──► API
#                                   │ Pipe can't start it 3x        │ an image still failing        (records sizes)
#                                   ▼                               ▼
#                               dead-letter queue ◄─────────────────┘ ──alarm──► SNS ──► email
#
# Why a queue instead of S3 invoking the function directly (item 27): a
# burst of uploads waits in the queue instead of hitting the account's
# 10-concurrent-execution limit; a failure retries one message, not a whole
# event; and a message that keeps failing is parked, kept 14 days and
# reported, instead of disappearing after S3's two async retries.
#
# Cost, inside the always-free allowance: SQS includes 1M requests a month.
# Idle, the Pipe long-polls the uploads queue and the API long-polls
# results (~130k a month). SNS
# includes 1,000 emails; CloudWatch, 10 alarms. SSE-SQS encryption is free.

locals {
  uploads_queue_name = "${var.project}-media-uploads"
  # Long enough that a message isn't handed out twice while the Pipe is
  # still starting its execution (seconds, normally).
  uploads_visibility_timeout = 6 * local.function_timeout_seconds
}

resource "aws_sqs_queue" "uploads_dlq" {
  name                      = "${local.uploads_queue_name}-dlq"
  message_retention_seconds = 14 * 24 * 3600 # the maximum: time to look before it's gone
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "uploads" {
  name                       = local.uploads_queue_name
  visibility_timeout_seconds = local.uploads_visibility_timeout
  message_retention_seconds  = 4 * 24 * 3600
  # S3 can only deliver to an encrypted queue with SSE-SQS (or a customer
  # KMS key, $1/month); the AWS-managed SQS KMS key would refuse it.
  sqs_managed_sse_enabled = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.uploads_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Only this account's media bucket may send to the uploads queue.
data "aws_iam_policy_document" "uploads_queue" {
  statement {
    sid       = "MediaBucketNotifications"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.uploads.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [data.aws_s3_bucket.media.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "uploads" {
  queue_url = aws_sqs_queue.uploads.id
  policy    = data.aws_iam_policy_document.uploads_queue.json
}

# Where finished work is reported. The API polls it (app/media/), because
# AWS can't reach a database on a laptop; on ECS it would work the same.
resource "aws_sqs_queue" "results" {
  name                       = "${var.project}-media-results"
  message_retention_seconds  = 14 * 24 * 3600 # the API may be off for days
  visibility_timeout_seconds = 60
  sqs_managed_sse_enabled    = true
}

resource "aws_sns_topic" "media_alerts" {
  # checkov:skip=CKV_AWS_26: CloudWatch can't publish to a topic encrypted with the AWS-managed SNS key; a customer key is $1/month, and the alarm carries no secrets
  name = "${var.project}-media-alerts"
}

resource "aws_sns_topic_subscription" "media_alert_email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.media_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Anything in the dead-letter queue is an upload that still failed after
# its retries (parked by the workflow, or by SQS if the Pipe couldn't start it).
resource "aws_cloudwatch_metric_alarm" "uploads_dead_letters" {
  alarm_name          = "${local.uploads_queue_name}-dead-letters"
  alarm_description   = "An image upload was parked in ${aws_sqs_queue.uploads_dlq.name} after its retries. Its message attributes name the error and the workflow execution; fix, then redrive the queue."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.uploads_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  # An empty dead-letter queue publishes no data points; that's the good case.
  treat_missing_data = "notBreaching"
  alarm_actions      = [aws_sns_topic.media_alerts.arn]
  ok_actions         = [aws_sns_topic.media_alerts.arn]
}

# The API's AWS user (infra/account/app_user.tf) may read and delete results,
# nothing else here. At go-live this moves to the ECS task role.
data "aws_iam_policy_document" "app_results" {
  statement {
    sid       = "ConsumeResults"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.results.arn]
  }
}

resource "aws_iam_policy" "app_results" {
  name        = "${var.project}-app-media-results"
  description = "Lets the API consume image-variant results (infra/media-pipeline/queue.tf)."
  policy      = data.aws_iam_policy_document.app_results.json
}

resource "aws_iam_user_policy_attachment" "app_results" {
  # checkov:skip=CKV_AWS_40: the one machine user, as in infra/account/app_user.tf; a group would only add indirection. ECS uses a task role instead
  user       = var.app_user_name
  policy_arn = aws_iam_policy.app_results.arn
}
