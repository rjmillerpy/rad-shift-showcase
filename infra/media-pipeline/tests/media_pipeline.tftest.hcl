# Offline tests (mock AWS provider): what the function may touch, what
# triggers it, that it can never trigger itself, and that failures are
# retried, parked and reported (item 28).
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
  override_data {
    target = data.aws_iam_policy_document.uploads_queue
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.app_results
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.image_variants
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_resource {
    target = aws_sns_topic.media_alerts
    values = { arn = "arn:aws:sns:us-east-2:123456789012:radshift-media-alerts" }
  }
  override_resource {
    target = aws_iam_policy.app_results
    values = { arn = "arn:aws:iam::123456789012:policy/radshift-app-media-results" }
  }
  override_resource {
    target = aws_iam_role.image_variants
    values = { arn = "arn:aws:iam::123456789012:role/radshift-image-variants" }
  }
  override_resource {
    target = aws_lambda_function.image_variants
    values = { arn = "arn:aws:lambda:us-east-2:123456789012:function:radshift-image-variants" }
  }
  override_resource {
    target = aws_cloudwatch_log_group.image_variants
    values = { arn = "arn:aws:logs:us-east-2:123456789012:log-group:/aws/lambda/radshift-image-variants" }
  }
  override_data {
    target = data.aws_iam_policy_document.states_trust
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.pipes_trust
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.media_workflow
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.uploads_pipe
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_resource {
    target = aws_iam_role.media_workflow
    values = { arn = "arn:aws:iam::123456789012:role/radshift-media" }
  }
  override_resource {
    target = aws_iam_role.uploads_pipe
    values = { arn = "arn:aws:iam::123456789012:role/radshift-media-uploads-pipe" }
  }
  override_resource {
    target = aws_cloudwatch_log_group.media_workflow
    values = { arn = "arn:aws:logs:us-east-2:123456789012:log-group:/aws/vendedlogs/states/radshift-media" }
  }
  override_resource {
    target = aws_sfn_state_machine.media
    values = { arn = "arn:aws:states:us-east-2:123456789012:stateMachine:radshift-media" }
  }
  override_resource {
    target = aws_sqs_queue.uploads
    values = {
      arn = "arn:aws:sqs:us-east-2:123456789012:radshift-media-uploads"
      url = "https://sqs.us-east-2.amazonaws.com/123456789012/radshift-media-uploads"
    }
  }
  override_resource {
    target = aws_sqs_queue.uploads_dlq
    values = { arn = "arn:aws:sqs:us-east-2:123456789012:radshift-media-uploads-dlq" }
  }
  override_resource {
    target = aws_sqs_queue.results
    values = {
      arn = "arn:aws:sqs:us-east-2:123456789012:radshift-media-results"
      url = "https://sqs.us-east-2.amazonaws.com/123456789012/radshift-media-results"
    }
  }
}

variables {
  lambda_zip = "tests/fixtures/placeholder.zip"
  # Set here so a local media.auto.tfvars never changes what's tested.
  alert_email = ""
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

run "only_post_images_reach_the_queue" {
  command = apply

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_notification.media.queue :
      rule.filter_prefix == "posts/" && contains([".jpg", ".jpeg", ".png", ".webp"], rule.filter_suffix)
    ])
    error_message = "Only images under posts/ are queued (videos and documents would be wasted work)."
  }
  assert {
    condition     = length(aws_s3_bucket_notification.media.queue) == 4
    error_message = "One rule per image suffix."
  }
  assert {
    condition     = length(aws_s3_bucket_notification.media.lambda_function) == 0
    error_message = "S3 no longer invokes the function directly; everything goes through the queue."
  }
  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_notification.media.queue :
      rule.queue_arn == aws_sqs_queue.uploads.arn
    ])
    error_message = "Every rule targets the uploads queue."
  }
}

run "only_this_accounts_bucket_may_queue" {
  command = plan

  assert {
    condition = (
      toset(flatten(data.aws_iam_policy_document.uploads_queue.statement[0].condition[*].values))
      == toset(["arn:aws:s3:::radshift-bucket", "123456789012"])
    )
    error_message = "Only this bucket, in this account, may send (a bucket name can be re-registered by anyone)."
  }
  assert {
    condition     = data.aws_iam_policy_document.uploads_queue.statement[0].actions == toset(["sqs:SendMessage"])
    error_message = "S3 may only send to the queue."
  }
}

run "failures_are_retried_parked_and_reported" {
  command = apply

  assert {
    condition     = jsondecode(aws_sqs_queue.uploads.redrive_policy).maxReceiveCount == 3
    error_message = "Three attempts, then the dead-letter queue."
  }
  assert {
    condition     = jsondecode(aws_sqs_queue.uploads.redrive_policy).deadLetterTargetArn == aws_sqs_queue.uploads_dlq.arn
    error_message = "Failures go to this stack's dead-letter queue."
  }
  assert {
    condition     = aws_sqs_queue.uploads.visibility_timeout_seconds >= 6 * aws_lambda_function.image_variants.timeout
    error_message = "Visibility timeout at least 6x the function's, or a slow batch is handed out twice."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.uploads_dead_letters.dimensions.QueueName == "radshift-media-uploads-dlq"
    error_message = "The alarm watches the dead-letter queue."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.uploads_dead_letters.alarm_actions == toset([aws_sns_topic.media_alerts.arn])
    error_message = "The alarm emails through the media alerts topic."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.uploads_dead_letters.treat_missing_data == "notBreaching"
    error_message = "An empty dead-letter queue sends no data; that is not an alarm."
  }
  assert {
    condition     = alltrue([aws_sqs_queue.uploads.sqs_managed_sse_enabled, aws_sqs_queue.uploads_dlq.sqs_managed_sse_enabled, aws_sqs_queue.results.sqs_managed_sse_enabled])
    error_message = "Every queue is encrypted at rest (SSE-SQS is free and S3 can deliver to it)."
  }
}

run "no_email_without_an_address" {
  command = plan

  assert {
    condition     = length(aws_sns_topic_subscription.media_alert_email) == 0
    error_message = "No subscription unless alert_email is set (media.auto.tfvars)."
  }
}

run "an_address_subscribes_by_email" {
  command = apply

  variables {
    alert_email = "alerts@example.com"
  }

  assert {
    condition     = aws_sns_topic_subscription.media_alert_email[0].protocol == "email"
    error_message = "The alert is an email (SNS includes 1,000 a month)."
  }
}

run "the_api_user_may_only_consume_results" {
  command = apply

  assert {
    condition     = aws_iam_user_policy_attachment.app_results.user == "radshift-app"
    error_message = "The API's own user consumes results."
  }
  assert {
    condition     = data.aws_iam_policy_document.app_results.statement[0].actions == toset(["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"])
    error_message = "Receive and delete results, nothing else."
  }
}

run "a_workflow_runs_each_upload" {
  command = apply

  assert {
    condition     = aws_pipes_pipe.uploads.source == aws_sqs_queue.uploads.arn && aws_pipes_pipe.uploads.target == aws_sfn_state_machine.media.arn
    error_message = "The Pipe takes uploads off the queue and starts the workflow."
  }
  assert {
    condition     = aws_pipes_pipe.uploads.source_parameters[0].sqs_queue_parameters[0].batch_size == 1
    error_message = "One execution per notification, so each upload has its own history."
  }
  assert {
    condition     = aws_pipes_pipe.uploads.target_parameters[0].step_function_state_machine_parameters[0].invocation_type == "FIRE_AND_FORGET"
    error_message = "Standard workflows are started asynchronously."
  }
  assert {
    condition     = aws_sfn_state_machine.media.type == "STANDARD"
    error_message = "Standard: a free tier and 90 days of execution history (Express has neither)."
  }
  assert {
    condition     = aws_sfn_state_machine.media.logging_configuration[0].level == "ERROR" && !aws_sfn_state_machine.media.logging_configuration[0].include_execution_data
    error_message = "Log failures only, without keys or results."
  }
  assert {
    condition     = length(aws_lambda_function.image_variants.environment) == 0
    error_message = "The function no longer needs the results queue: the workflow reports."
  }
}

run "each_role_reaches_only_its_targets" {
  command = plan

  assert {
    condition     = data.aws_iam_policy_document.media_workflow.statement[1].actions == toset(["sqs:SendMessage"])
    error_message = "The workflow only sends: results, and parked failures."
  }
  assert {
    condition     = data.aws_iam_policy_document.uploads_pipe.statement[1].actions == toset(["states:StartExecution"])
    error_message = "The Pipe can start the workflow, not stop or read it."
  }
  assert {
    condition     = length(data.aws_iam_policy_document.image_variants.statement) == 3
    error_message = "The function reads uploads, writes variants and logs; no queue access."
  }
}

run "overlapping_prefixes_are_refused" {
  command = plan

  variables {
    variant_prefix = "posts/variants/"
  }

  expect_failures = [var.variant_prefix]
}
