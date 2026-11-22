# Item 29: the media workflow in Step Functions, started by an EventBridge
# Pipe for each queued upload (replacing item 28's Lambda event source).
#
#   uploads queue ──Pipe──► state machine: for each image
#                              MakeVariants (Lambda, retried with backoff)
#                              ├─ variants? ──► ReportResult (SQS results queue)
#                              ├─ nothing to report ──► done
#                              └─ still failing ──► ParkInDeadLetterQueue ──► Failed
#
# The Lambda only resizes; retries, reporting and failure handling are states
# you can see and replay in the console, one execution per upload.
#
# Cost: Standard workflows include 4,000 state transitions a month free; an
# image takes about 6, so ~650 images, then $0.025 per 1,000 transitions
# (~$0.00015 an image). Pipes have no free tier: $0.40 per million events
# (~$0.0000004 an image). The Pipe's SQS polling counts against SQS's 1M free
# requests, as the Lambda's pollers did.

locals {
  state_machine_name = "${var.project}-media"
}

data "aws_iam_policy_document" "states_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "media_workflow" {
  name               = local.state_machine_name
  assume_role_policy = data.aws_iam_policy_document.states_trust.json
}

# Invoke the one function, send to the two queues, write its own logs.
data "aws_iam_policy_document" "media_workflow" {
  statement {
    sid       = "ResizeImages"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.image_variants.arn, "${aws_lambda_function.image_variants.arn}:*"]
  }
  statement {
    sid       = "ReportAndPark"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.results.arn, aws_sqs_queue.uploads_dlq.arn]
  }
  statement {
    # Step Functions delivers logs through CloudWatch's log-delivery API,
    # which doesn't support resource-level permissions.
    sid = "DeliverLogs"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "media_workflow" {
  name   = "media-workflow"
  role   = aws_iam_role.media_workflow.id
  policy = data.aws_iam_policy_document.media_workflow.json
}

# nosemgrep: terraform.aws.security.aws-cloudwatch-log-group-unencrypted.aws-cloudwatch-log-group-unencrypted - encrypted at rest by default; a customer KMS key is $1/month
resource "aws_cloudwatch_log_group" "media_workflow" {
  # checkov:skip=CKV_AWS_158: CloudWatch encrypts logs at rest by default; a customer KMS key is $1/month
  # checkov:skip=CKV_AWS_338: debugging logs, kept 14 days on purpose (storage is billed)
  name              = "/aws/vendedlogs/states/${local.state_machine_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "media" {
  # checkov:skip=CKV_AWS_284: X-Ray costs beyond its free tier; every execution's full history is kept 90 days in Step Functions itself
  # checkov:skip=CKV_AWS_285: logs failures without execution data on purpose (object keys name users); the execution history has the data
  name     = local.state_machine_name
  role_arn = aws_iam_role.media_workflow.arn
  type     = "STANDARD" # Express has no free tier and keeps no execution history
  definition = templatefile("${path.module}/state_machine.asl.json", {
    function_arn          = aws_lambda_function.image_variants.arn
    results_queue_url     = aws_sqs_queue.results.url
    dead_letter_queue_url = aws_sqs_queue.uploads_dlq.url
    # The function's own timeout plus a margin for the invoke itself.
    task_timeout_seconds = local.function_timeout_seconds + 10
    max_attempts         = var.max_receive_count - 1
  })

  logging_configuration {
    # Failures only, and without the data (keys, results): enough to find
    # the execution, whose history has the rest.
    level                  = "ERROR"
    include_execution_data = false
    log_destination        = "${aws_cloudwatch_log_group.media_workflow.arn}:*"
  }

  depends_on = [aws_iam_role_policy.media_workflow]
}

data "aws_iam_policy_document" "pipes_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["pipes.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "uploads_pipe" {
  name               = "${var.project}-media-uploads-pipe"
  assume_role_policy = data.aws_iam_policy_document.pipes_trust.json
}

data "aws_iam_policy_document" "uploads_pipe" {
  statement {
    sid       = "ReadUploadsQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.uploads.arn]
  }
  statement {
    sid       = "StartWorkflow"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.media.arn]
  }
}

resource "aws_iam_role_policy" "uploads_pipe" {
  name   = "uploads-pipe"
  role   = aws_iam_role.uploads_pipe.id
  policy = data.aws_iam_policy_document.uploads_pipe.json
}

# One execution per queued notification. Fire and forget (the only mode a
# Standard workflow supports here): the message is deleted once the
# execution starts, so failures from then on are the workflow's to handle,
# and it parks them in the dead-letter queue itself. If the Pipe can't start
# an execution, the message stays and SQS's redrive parks it after
# max_receive_count tries.
resource "aws_pipes_pipe" "uploads" {
  name     = "${var.project}-media-uploads"
  role_arn = aws_iam_role.uploads_pipe.arn
  source   = aws_sqs_queue.uploads.arn
  target   = aws_sfn_state_machine.media.arn

  source_parameters {
    sqs_queue_parameters {
      batch_size = 1
    }
  }

  target_parameters {
    step_function_state_machine_parameters {
      invocation_type = "FIRE_AND_FORGET"
    }
  }

  depends_on = [aws_iam_role_policy.uploads_pipe]
}
