locals {
  http_port  = 80
  https_port = 443
  tls_policy = "ELBSecurityPolicy-TLS13-1-2-Res-PQ-2025-09"

  # HTTPS, the certificate and the DNS records exist only once there is a domain.
  https_enabled = var.domain_name != ""

  container_ports = {
    backend  = 5000 # uvicorn, see the Dockerfile CMD
    frontend = 3000 # Next.js standalone server
  }

  health_paths = {
    backend  = "/health"     # pings the database (item 7)
    frontend = "/api/health" # Next.js route
  }

  # Read by the backend (app/common/config.py and friends). Secrets come from
  # SSM Parameter Store instead (item 12 creates the parameters), so no secret
  # value is ever in Terraform, its state, or the task definition.
  # DB_PASSWORD is handled in database.tf: SSM in external mode, the
  # RDS-managed secret in rds mode.
  backend_ssm_secret_names = ["JWT_SECRET", "RESEND_API_KEY", "ANTHROPIC_API_KEY", "ADMIN_SECRET"]
  ssm_prefix               = "/${var.project}"

  account_id = data.aws_caller_identity.current.account_id
}
