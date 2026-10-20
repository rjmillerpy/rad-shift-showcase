# Human admin access (item 9): one Identity Center user with AdministratorAccess
# through 4-hour sessions (`aws sso login --profile radshift-admin`). No
# long-lived admin keys anywhere; root keeps only its password and MFA.

data "aws_ssoadmin_instances" "main" {
  provider = aws.identity_center
}

locals {
  sso_instance_arn  = one(data.aws_ssoadmin_instances.main.arns)
  identity_store_id = one(data.aws_ssoadmin_instances.main.identity_store_ids)
}

data "aws_identitystore_user" "admin" {
  provider          = aws.identity_center
  identity_store_id = local.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = var.admin_user_name
    }
  }
}

resource "aws_ssoadmin_permission_set" "admin" {
  provider         = aws.identity_center
  name             = "AdministratorAccess"
  description      = "Full admin for rad-shift work; short-lived via aws sso login"
  instance_arn     = local.sso_instance_arn
  session_duration = "PT4H"
  tags             = { project = "rad-shift" }
}

resource "aws_ssoadmin_managed_policy_attachment" "admin" {
  # checkov:skip=CKV_AWS_274: this is the account owner's admin login: 4-hour sessions through Identity Center, no long-lived keys
  provider           = aws.identity_center
  instance_arn       = local.sso_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.admin.arn
  managed_policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

resource "aws_ssoadmin_account_assignment" "admin" {
  provider           = aws.identity_center
  instance_arn       = local.sso_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.admin.arn
  principal_type     = "USER"
  principal_id       = data.aws_identitystore_user.admin.user_id
  target_type        = "AWS_ACCOUNT"
  target_id          = data.aws_caller_identity.current.account_id
}

# The permission set's ARN has a random suffix AWS chose, so it is the one
# id that has to be written out.
locals {
  admin_permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-7223ae0de344429f/ps-6ebf29ed5514c4e5"
}

import {
  to = aws_ssoadmin_permission_set.admin
  id = "${local.admin_permission_set_arn},${local.sso_instance_arn}"
}

import {
  to = aws_ssoadmin_managed_policy_attachment.admin
  id = "arn:aws:iam::aws:policy/AdministratorAccess,${local.admin_permission_set_arn},${local.sso_instance_arn}"
}

import {
  to = aws_ssoadmin_account_assignment.admin
  id = "${data.aws_identitystore_user.admin.user_id},USER,${data.aws_caller_identity.current.account_id},AWS_ACCOUNT,${local.admin_permission_set_arn},${local.sso_instance_arn}"
}
