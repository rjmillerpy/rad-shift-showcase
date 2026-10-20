# GitHub Actions gets short-lived AWS credentials without any stored key:
#  1. A workflow asks GitHub for an OIDC token: a JWT signed by GitHub saying
#     which repository, branch and workflow is running.
#  2. It calls sts:AssumeRoleWithWebIdentity with that token.
#  3. STS checks the signature against this OIDC provider and the claims
#     against the role's trust policy, then returns credentials that expire
#     within the hour.
# Nothing long-lived exists to leak, rotate or forget.

locals {
  github_oidc_host = "token.actions.githubusercontent.com"
  sts_audience     = "sts.amazonaws.com" # what aws-actions/configure-aws-credentials requests

  # GitHub's `sub` claim for a run on a branch: repo:<owner>/<name>:ref:refs/heads/<branch>.
  # Pull requests, other branches, tags and forks get a different `sub`, so
  # they can't assume the role. (A job that names a GitHub environment gets
  # repo:<owner>/<name>:environment:<env> instead, so the workflows use none.)
  deploy_subjects = {
    for key, repo in var.deploy_repositories : key => "repo:${repo.repository}:ref:refs/heads/${var.deploy_branch}"
  }

  one_hour_seconds = 3600
}

# One per account per issuer. No thumbprint: AWS verifies GitHub's certificate
# against its own trusted CAs, so the old thumbprint list is ignored.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.github_oidc_host}"
  client_id_list = [local.sts_audience]
}

# One role per repository, so each repository's workflows get only the
# permissions granted to its own role (registry/: each pushes its own image).
resource "aws_iam_role" "github_deploy" {
  for_each = var.deploy_repositories

  name                 = each.value.role_name
  description          = "Assumed by GitHub Actions on ${each.value.repository}@${var.deploy_branch} via OIDC."
  max_session_duration = local.one_hour_seconds

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "GitHubActionsOnOneBranch"
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        # StringEquals, not StringLike: no wildcard can widen either claim.
        StringEquals = {
          "${local.github_oidc_host}:aud" = local.sts_audience
          "${local.github_oidc_host}:sub" = local.deploy_subjects[each.key]
        }
      }
    }]
  })
}

# Item 13 created the backend role as a single resource; for_each gives it a
# key. Without this block Terraform would destroy the role and create a new
# one (and the backend repository's AWS_DEPLOY_ROLE_ARN would still work only
# because the name, and so the ARN, happens to be the same).
moved {
  from = aws_iam_role.github_deploy
  to   = aws_iam_role.github_deploy["backend"]
}

# No permission policies here, on purpose. Each stack that owns resources
# grants access to exactly those: registry/ (push and pull images, item 17)
# and, at go-live, the main stack (ECS deploy, infra/deploy_role.tf).
