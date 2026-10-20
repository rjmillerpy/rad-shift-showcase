output "load_balancer_dns_name" {
  description = "Point api_hostname and the app's host name here (item 14 adds Route 53 records)."
  value       = aws_lb.main.dns_name
}

output "database_endpoint" {
  description = "Where the backend connects (the RDS address in rds mode)."
  value       = local.db_host
}

output "cluster_name" {
  description = "ECS cluster the CD pipeline deploys to (item 17: aws ecs update-service --cluster)."
  value       = aws_ecs_cluster.main.name
}

output "ssm_parameters_expected" {
  description = "Parameters item 12 must create (SecureString) before the backend can start."
  value = [for name in concat(local.backend_ssm_secret_names, local.use_rds ? [] : [local.db_password_secret_name]) :
  "${local.ssm_prefix}/${name}"]
}
