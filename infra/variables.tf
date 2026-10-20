variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "radshift"
}

variable "region" {
  description = "AWS region. us-east-2 because the existing media bucket lives there (no cross-region transfer charges)."
  type        = string
  default     = "us-east-2"
}

variable "availability_zones" {
  description = "Two AZs for the load balancer and tasks (an ALB requires at least two)."
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two availability zones: an ALB needs two, and more only adds public IPs."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC; the two public subnets are carved out of it."
  type        = string
  default     = "10.20.0.0/16"
}

variable "api_hostname" {
  description = "Host name the load balancer routes to the backend (e.g. api.example.com). Everything else goes to the frontend."
  type        = string
}

variable "app_url" {
  description = "Public URL of the frontend; the backend uses it in emails and for CORS."
  type        = string
}

variable "backend_image_tag" {
  description = "Tag of the backend image in ECR (CI pushes one per commit, item 17)."
  type        = string
}

variable "frontend_image_tag" {
  description = "Tag of the frontend image in ECR. NEXT_PUBLIC_API_URL is baked in at build time, so build it with https://<api_hostname>."
  type        = string
}

variable "backend_cpu" {
  description = "Backend task CPU units (1024 = 1 vCPU). The scraping browsers need about 1 vCPU / 2 GB."
  type        = number
  default     = 1024
}

variable "backend_memory" {
  description = "Backend task memory in MiB."
  type        = number
  default     = 2048
}

variable "frontend_cpu" {
  description = "Frontend task CPU units."
  type        = number
  default     = 256
}

variable "frontend_memory" {
  description = "Frontend task memory in MiB."
  type        = number
  default     = 512
}

variable "backend_desired_count" {
  description = "Backend tasks. Must stay 1: every API process starts the generator scheduler, so two tasks would scrape twice."
  type        = number
  default     = 1

  validation {
    condition     = var.backend_desired_count == 1
    error_message = "backend_desired_count must be 1 until the generator scheduler runs as its own service."
  }
}

variable "use_fargate_spot" {
  description = "Run tasks on Fargate Spot (~70% cheaper; AWS can stop a task with two minutes' notice). Fine for a demo, not for production traffic."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Logs are billed per GB stored, so keep it short."
  type        = number
  default     = 14
}

variable "media_bucket_name" {
  description = "Existing S3 bucket for uploaded media (created outside Terraform; import it in item 16)."
  type        = string
  default     = "radshift-bucket"
}

variable "database_mode" {
  description = "\"external\": any Postgres you point db_host at (Neon's free plan is the $0 option); its password comes from SSM. \"rds\": Terraform creates an RDS instance whose password RDS generates and keeps in Secrets Manager."
  type        = string
  default     = "external"

  validation {
    condition     = contains(["external", "rds"], var.database_mode)
    error_message = "database_mode must be \"external\" or \"rds\"."
  }
}

variable "db_host" {
  description = "Host of the external database (database_mode = \"external\"). Ignored in rds mode."
  type        = string
  default     = ""

  validation {
    condition     = var.database_mode == "rds" || var.db_host != ""
    error_message = "Set db_host when database_mode is \"external\"."
  }
}

variable "db_instance_class" {
  description = "RDS instance size (rds mode). db.t4g.micro: 2 vCPU burstable, 1 GB, ~$12/month."
  type        = string
  default     = "db.t4g.micro"
}

variable "protect_from_deletion" {
  description = "Block `terraform destroy` from deleting the load balancer and the RDS instance. Turn off deliberately (a throwaway practice stack), never by accident."
  type        = bool
  default     = true
}

variable "db_name" {
  description = "Database name."
  type        = string
  default     = "radshift"
}

variable "db_user" {
  description = "Database user."
  type        = string
  default     = "radshift"
}

variable "from_email" {
  description = "Sender address for verification emails (Resend)."
  type        = string
}

variable "github_deploy_role_name" {
  description = "The GitHub Actions OIDC role created by infra/github-oidc/ (its deploy_role_name output)."
  type        = string
  default     = "radshift-github-deploy"
}

variable "alert_email" {
  description = "Where the CloudWatch alarms email (monitoring.tf). Empty: alarms still record state, but nobody is notified. AWS emails a confirmation link first."
  type        = string
  default     = ""
}

variable "error_rate_threshold_percent" {
  description = "Alarm when more than this share of API requests fail with a 5xx. Same as the local Prometheus rule (observability/prometheus/alerts.yml)."
  type        = number
  default     = 5
}

variable "domain_name" {
  description = "The site's domain (its Route 53 hosted zone must exist). Empty: no certificate, no DNS records, HTTP only. Set at go-live to get HTTPS."
  type        = string
  default     = ""
}
