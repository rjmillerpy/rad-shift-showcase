# Two roles per ECS task, a distinction interviewers ask about:
#  - execution role: used by ECS itself to pull the image, write logs and
#    read the secrets it injects. The app never holds these permissions.
#  - task role: what the app's own code can do. For the backend, the same
#    four S3 actions as the radshift-app IAM user used locally (item 9).

locals {
  ecs_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        # Only tasks in this account (confused-deputy protection).
        StringEquals = { "aws:SourceAccount" = local.account_id }
      }
    }]
  })
}

resource "aws_iam_role" "execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = local.ecs_trust_policy
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "read-app-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "ReadOnlyThisAppsParameters"
      Effect   = "Allow"
      Action   = ["ssm:GetParameters"]
      Resource = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${local.ssm_prefix}/*"
    }]
  })
}

resource "aws_iam_role" "backend_task" {
  name               = "${var.project}-backend-task"
  assume_role_policy = local.ecs_trust_policy
}

resource "aws_iam_role_policy" "backend_media" {
  name = "media-objects-in-one-bucket"
  role = aws_iam_role.backend_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "MediaObjectsInOneBucket"
      Effect = "Allow"
      # nosemgrep: terraform.lang.security.iam.no-iam-resource-exposure.no-iam-resource-exposure - PutObjectAcl sets public-read on uploaded media, which is served directly by design; one bucket only
      Action   = ["s3:PutObject", "s3:PutObjectAcl", "s3:GetObject", "s3:AbortMultipartUpload"]
      Resource = "arn:aws:s3:::${var.media_bucket_name}/*"
    }]
  })
}

# The frontend server calls nothing in AWS, so its task role has no policies.
resource "aws_iam_role" "frontend_task" {
  name               = "${var.project}-frontend-task"
  assume_role_policy = local.ecs_trust_policy
}
