output "app_user_name" {
  description = "IAM user for the local stack's S3 access; its key is created outside Terraform."
  value       = aws_iam_user.app.name
}

output "admin_permission_set_arn" {
  description = "The permission set behind the radshift-admin SSO profile."
  value       = aws_ssoadmin_permission_set.admin.arn
}
