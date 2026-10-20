# Alarms (roadmap item 15): the go-live twin of the local Prometheus rules in
# observability/prometheus/alerts.yml, built on metrics the ALB publishes for
# free. Cost when applied: $0.10 per metric per alarm per month (the error
# rate uses two metrics, so $0.30 in all); SNS email is free for the first
# 1,000 a month. Logs are already in CloudWatch (logs.tf, the awslogs driver).

locals {
  # 5 one-minute periods, as the Prometheus rule's `for: 5m`.
  alarm_period_seconds     = 60
  alarm_evaluation_periods = 5
  backend_target_group_dims = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.app["backend"].arn_suffix
  }
}

resource "aws_sns_topic" "alerts" {
  # checkov:skip=CKV_AWS_26: CloudWatch can't publish to a topic encrypted with the AWS-managed SNS key; a customer key is $1/month, and alerts carry no secrets
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "alert_email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Share of backend requests answered with a 5xx. Counts the target's own 5xx
# (HTTPCode_Target_5XX_Count), not the ALB's (502/503 when no target is
# healthy); the unhealthy-host alarm below covers that case.
resource "aws_cloudwatch_metric_alarm" "backend_error_rate" {
  alarm_name          = "${var.project}-backend-5xx-rate"
  alarm_description   = "More than ${var.error_rate_threshold_percent}% of API requests failed with a 5xx for 5 minutes."
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.error_rate_threshold_percent
  evaluation_periods  = local.alarm_evaluation_periods
  # No requests is not an outage: missing data counts as fine. A dead backend
  # is caught by the unhealthy-host alarm instead.
  treat_missing_data = "notBreaching"
  alarm_actions      = [aws_sns_topic.alerts.arn]
  ok_actions         = [aws_sns_topic.alerts.arn]

  metric_query {
    id          = "error_rate"
    expression  = "100 * errors / requests"
    label       = "5xx %"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = local.backend_target_group_dims
      period      = local.alarm_period_seconds
      stat        = "Sum"
    }
  }

  metric_query {
    id = "requests"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      dimensions  = local.backend_target_group_dims
      period      = local.alarm_period_seconds
      stat        = "Sum"
    }
  }
}

# The BackendDown twin: the ALB's health check (/health, which pings the
# database) is failing on the backend's one task.
resource "aws_cloudwatch_metric_alarm" "backend_unhealthy" {
  alarm_name          = "${var.project}-backend-unhealthy"
  alarm_description   = "The backend's health check has failed for 5 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  dimensions          = local.backend_target_group_dims
  statistic           = "Maximum"
  period              = local.alarm_period_seconds
  evaluation_periods  = local.alarm_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  # No data means the target group reports nothing at all, as during a
  # deploy that replaces the only task; treat that as a problem too.
  treat_missing_data = "breaching"
  alarm_actions      = [aws_sns_topic.alerts.arn]
  ok_actions         = [aws_sns_topic.alerts.arn]
}
