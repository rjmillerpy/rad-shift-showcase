variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "radshift"
}

variable "region" {
  description = "AWS region for the provider. IAM is global; this only picks the API endpoint."
  type        = string
  default     = "us-east-2"
}

variable "deploy_repositories" {
  description = "The repositories whose workflows may deploy, each with its own role. Keyed by component; registry/ refers to the keys."
  type = map(object({
    repository = string # owner/name
    role_name  = string
  }))
  default = {
    # Item 13's role; its name is kept so its ARN (a repository variable) stays valid.
    backend  = { repository = "rjmillerpy/rad-shift", role_name = "radshift-github-deploy" }
    frontend = { repository = "rjmillerpy/rad-shift-frontend", role_name = "radshift-frontend-github-deploy" }
  }

  validation {
    condition     = alltrue([for repo in values(var.deploy_repositories) : can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", repo.repository))])
    error_message = "Each repository must be owner/name, with no wildcards."
  }
}

variable "deploy_branch" {
  description = "The one branch whose workflows may assume the deploy role."
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+$", var.deploy_branch))
    error_message = "deploy_branch must be a plain branch name, with no wildcards."
  }
}
