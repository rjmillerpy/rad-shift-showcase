output "deploy_role_arns" {
  description = "Per repository: set as that repository's AWS_DEPLOY_ROLE_ARN variable (not a secret: an ARN grants nothing on its own)."
  value       = { for key, role in aws_iam_role.github_deploy : key => role.arn }
}

output "deploy_role_names" {
  description = "Per repository: registry/ and, at go-live, the main stack (infra/deploy_role.tf) attach permissions to these roles."
  value       = { for key, role in aws_iam_role.github_deploy : key => role.name }
}

output "oidc_provider_arn" {
  description = "GitHub's OIDC identity provider in this account; any further CI roles trust it."
  value       = aws_iam_openid_connect_provider.github.arn
}
