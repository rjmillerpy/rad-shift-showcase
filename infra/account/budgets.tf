# Cost alarms (item 9). Free: the first two budgets per account cost nothing.
locals {
  # (type, threshold %) pairs: actual spend at 80% and 100%, and the
  # forecast for the month at 100% (an early warning, days ahead).
  budget_notifications = [
    { type = "ACTUAL", threshold = 80 },
    { type = "ACTUAL", threshold = 100 },
    { type = "FORECASTED", threshold = 100 },
  ]
}

resource "aws_budgets_budget" "monthly" {
  for_each = var.monthly_budgets_usd

  name         = each.key
  budget_type  = "COST"
  limit_amount = format("%.1f", each.value)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = local.budget_notifications
    content {
      notification_type          = notification.value.type
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }
}

import {
  for_each = var.monthly_budgets_usd
  to       = aws_budgets_budget.monthly[each.key]
  id       = "${data.aws_caller_identity.current.account_id}:${each.key}"
}

data "aws_caller_identity" "current" {}
