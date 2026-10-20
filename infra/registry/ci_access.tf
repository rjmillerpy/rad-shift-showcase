# What each repository's CI role may do here: push its own image, and, for
# the repository that deploys, pull every image. The roles themselves (and
# who may assume them) are in github-oidc/.

locals {
  # docker push checks which layers exist, uploads the rest, then writes the
  # manifest; BatchGetImage lets it read a manifest back.
  push_actions = [
    "ecr:BatchCheckLayerAvailability",
    "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart",
    "ecr:CompleteLayerUpload",
    "ecr:PutImage",
    "ecr:BatchGetImage",
  ]
  pull_actions = [
    "ecr:BatchCheckLayerAvailability",
    "ecr:GetDownloadUrlForLayer",
    "ecr:BatchGetImage",
  ]
  # Publish skips a tag that already exists (tags are immutable, so pushing
  # it again would fail); deploy finds the newest image.
  describe_actions = ["ecr:DescribeImages"]

  all_repository_arns = [for repo in aws_ecr_repository.app : repo.arn]
}

resource "aws_iam_role_policy" "ci" {
  for_each = var.ci_roles

  name = "ecr-${each.key}"
  role = each.value.role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          # Logging in to ECR is account-wide; AWS has no narrower resource for it.
          Sid      = "EcrLogin"
          Effect   = "Allow"
          Action   = ["ecr:GetAuthorizationToken"]
          Resource = "*"
        },
        {
          Sid      = "PushOwnImage"
          Effect   = "Allow"
          Action   = concat(local.push_actions, local.describe_actions)
          Resource = aws_ecr_repository.app[each.key].arn
        },
      ],
      each.value.deploys ? [{
        Sid      = "PullEveryImageToDeploy"
        Effect   = "Allow"
        Action   = concat(local.pull_actions, local.describe_actions)
        Resource = local.all_repository_arns
      }] : [],
    )
  })
}
