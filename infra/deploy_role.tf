# Go-live permissions for the GitHub Actions deploy role (item 17's CD job).
# The role itself lives in github-oidc/; pushing and pulling images is granted
# by registry/, which owns the repositories. This stack owns the ECS services,
# so it grants access to exactly those, and the grant arrives with them.

locals {
  ecs_tasks_service = "ecs-tasks.amazonaws.com"
}

resource "aws_iam_role_policy" "github_deploy" {
  name = "deploy-services"
  role = var.github_deploy_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Task definitions have no per-resource permissions for these two calls.
        Sid      = "RegisterTaskDefinitions"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
        Resource = "*"
      },
      {
        Sid      = "DeployThisAppsServices"
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = [aws_ecs_service.backend.id, aws_ecs_service.frontend.id]
      },
      {
        # A new task definition names its roles, so CI must be able to pass
        # them, but only these three and only to ECS tasks. Without the
        # condition, PassRole is a privilege escalation.
        Sid    = "PassOnlyThisAppsTaskRoles"
        Effect = "Allow"
        # nosemgrep: terraform.lang.security.iam.no-iam-resource-exposure.no-iam-resource-exposure - three named roles, ECS tasks only (condition below)
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.execution.arn, aws_iam_role.backend_task.arn, aws_iam_role.frontend_task.arn]
        Condition = {
          StringEquals = { "iam:PassedToService" = local.ecs_tasks_service }
        }
      },
    ]
  })
}
