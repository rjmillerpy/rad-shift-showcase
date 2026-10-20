# Offline tests on a mock provider: no credentials, nothing created or
# imported in AWS. Run: terraform test (from infra/account/).

mock_provider "aws" {
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  # Mocked data sources return random strings; IAM validates policy JSON.
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::123456789012:policy/radshift-app-media" }
  }
}

mock_provider "aws" {
  alias = "identity_center"

  override_data {
    target = data.aws_ssoadmin_instances.main
    values = {
      arns               = ["arn:aws:sso:::instance/ssoins-0000000000000000"]
      identity_store_ids = ["d-0000000000"]
    }
  }
  override_data {
    target = data.aws_identitystore_user.admin
    values = { user_id = "00000000-0000-0000-0000-000000000000" }
  }
  mock_resource "aws_ssoadmin_permission_set" {
    defaults = { arn = "arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-0000000000000000" }
  }
}

# Mock providers can't import, so every resource adopted by an `import`
# block gets a stand-in. Configured arguments still come from the code.
override_resource {
  target = aws_budgets_budget.monthly
}
override_resource {
  target = aws_iam_policy.app_media
  values = { arn = "arn:aws:iam::123456789012:policy/radshift-app-media" }
}
override_resource {
  target = aws_iam_user.app
}
override_resource {
  target = aws_iam_user_policy_attachment.app_media
}
override_resource {
  target = aws_ssoadmin_permission_set.admin
  values = { arn = "arn:aws:sso:::permissionSet/ssoins-0000000000000000/ps-0000000000000000" }
}
override_resource {
  target = aws_ssoadmin_managed_policy_attachment.admin
}
override_resource {
  target = aws_ssoadmin_account_assignment.admin
}

variables {
  budget_alert_email = "alerts@test.example"
}

run "budgets_warn_early_and_at_the_limit" {
  assert {
    condition     = toset(keys(aws_budgets_budget.monthly)) == toset(["radshift-monthly-5", "radshift-monthly-20"])
    error_message = "A $5 tripwire and a $20 ceiling."
  }
  assert {
    condition = alltrue([
      for budget in aws_budgets_budget.monthly : toset([
        for n in budget.notification : "${n.notification_type}:${n.threshold}"
      ]) == toset(["ACTUAL:80", "ACTUAL:100", "FORECASTED:100"])
    ])
    error_message = "Each budget emails at 80% and 100% of actual spend and when the forecast passes 100%."
  }
  assert {
    condition = alltrue(flatten([
      for budget in aws_budgets_budget.monthly : [
        for n in budget.notification : n.subscriber_email_addresses == toset(["alerts@test.example"])
      ]
    ]))
    error_message = "Every notification goes to budget_alert_email."
  }
}

run "rejects_a_malformed_email" {
  command = plan
  variables { budget_alert_email = "not-an-email" }
  expect_failures = [var.budget_alert_email]
}

run "app_user_can_touch_one_bucket_and_four_actions" {
  assert {
    condition     = length(data.aws_iam_policy_document.app_media.statement) == 1
    error_message = "One statement only."
  }
  assert {
    condition = (
      toset(one(data.aws_iam_policy_document.app_media.statement).actions) ==
      toset(["s3:PutObject", "s3:PutObjectAcl", "s3:GetObject", "s3:AbortMultipartUpload"])
    )
    error_message = "Exactly the four object actions the app uses."
  }
  assert {
    condition     = toset(one(data.aws_iam_policy_document.app_media.statement).resources) == toset(["arn:aws:s3:::radshift-bucket/*"])
    error_message = "Objects in the media bucket only; never the bucket itself or s3:*."
  }
}

run "admin_sessions_are_short_lived" {
  assert {
    condition     = aws_ssoadmin_permission_set.admin.session_duration == "PT4H"
    error_message = "Admin credentials expire after 4 hours."
  }
  assert {
    condition     = aws_ssoadmin_account_assignment.admin.principal_type == "USER" && aws_ssoadmin_account_assignment.admin.target_id == "123456789012"
    error_message = "One named user, this account only."
  }
}
