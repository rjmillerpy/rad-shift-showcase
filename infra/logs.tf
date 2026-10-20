# nosemgrep: terraform.aws.security.aws-cloudwatch-log-group-unencrypted.aws-cloudwatch-log-group-unencrypted - encrypted at rest by default; a customer KMS key is $1/month
resource "aws_cloudwatch_log_group" "app" {
  # checkov:skip=CKV_AWS_158: CloudWatch encrypts logs at rest by default; a customer KMS key is $1/month
  # checkov:skip=CKV_AWS_338: 14-day retention is a deliberate cost guard (var.log_retention_days)
  for_each = local.container_ports

  name              = "/ecs/${var.project}/${each.key}"
  retention_in_days = var.log_retention_days
}
