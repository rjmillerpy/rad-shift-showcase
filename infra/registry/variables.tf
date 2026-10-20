variable "project" {
  description = "Name prefix for every resource. Repositories are <project>-<component>, the names the main stack looks up."
  type        = string
  default     = "radshift"
}

variable "region" {
  description = "AWS region for the repositories; the same as the main stack's, so ECS pulls without cross-region transfer."
  type        = string
  default     = "us-east-2"
}

variable "ci_roles" {
  description = <<-EOT
    One image per component, pushed by that repository's GitHub OIDC role
    (github-oidc/, its deploy_role_names output). `deploys` marks the
    repository whose deploy workflow runs the whole stack, so its role may
    also pull every image.
  EOT
  type = map(object({
    role_name = string
    deploys   = bool
  }))
  default = {
    backend  = { role_name = "radshift-github-deploy", deploys = true }
    frontend = { role_name = "radshift-frontend-github-deploy", deploys = false }
  }
}

variable "images_kept" {
  description = "Newest images kept per repository; older ones expire. Each is a possible rollback target."
  type        = number
  default     = 10

  validation {
    condition     = var.images_kept >= 2
    error_message = "Keep at least 2 images, or there is nothing to roll back to."
  }
}
