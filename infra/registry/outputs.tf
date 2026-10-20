output "repository_urls" {
  description = "Where each image is pushed: <registry>/<project>-<component>."
  value       = { for name, repo in aws_ecr_repository.app : name => repo.repository_url }
}

output "registry" {
  description = "The account's registry host, for docker login (the deploy workflow derives it the same way)."
  value       = split("/", values(aws_ecr_repository.app)[0].repository_url)[0]
}
