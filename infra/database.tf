# Item 11. database_mode = "external" (default, $0): Neon or any Postgres at
# db_host, nothing created here. database_mode = "rds": a small RDS Postgres
# in two private subnets, reachable only from the ECS tasks.
# Cost in rds mode at go-live: ~$12 instance + ~$2 for 20 GB gp3 + $0.40 for
# the RDS-managed secret; backups up to the database's size are free.

locals {
  use_rds = var.database_mode == "rds"

  private_subnets = {
    for index, az in var.availability_zones :
    az => cidrsubnet(var.vpc_cidr, 8, index + 10)
  }

  postgres_port           = 5432
  postgres_major          = "16" # same major as compose.yaml's postgres:16
  db_storage_gb           = 20
  db_storage_max_gb       = 50 # storage autoscaling ceiling
  db_backup_retention     = 7
  db_password_secret_name = "DB_PASSWORD"
}

# Private subnets: no route to the internet (the database never needs one).
# They are free, so they exist in both modes.
resource "aws_subnet" "private" {
  for_each = local.private_subnets

  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = each.value

  tags = { Name = "${var.project}-private-${each.key}" }
}

resource "aws_db_subnet_group" "main" {
  count = local.use_rds ? 1 : 0

  name       = var.project
  subnet_ids = [for subnet in aws_subnet.private : subnet.id]
}

resource "aws_security_group" "db" {
  count = local.use_rds ? 1 : 0

  name        = "${var.project}-db"
  description = "Postgres: reachable only from the ECS tasks"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_tasks" {
  count = local.use_rds ? 1 : 0

  security_group_id            = aws_security_group.db[0].id
  description                  = "Postgres from the ECS tasks only"
  ip_protocol                  = "tcp"
  from_port                    = local.postgres_port
  to_port                      = local.postgres_port
  referenced_security_group_id = aws_security_group.tasks.id
}

resource "aws_db_parameter_group" "main" {
  count = local.use_rds ? 1 : 0

  name   = "${var.project}-postgres${local.postgres_major}"
  family = "postgres${local.postgres_major}"

  parameter {
    name  = "rds.force_ssl" # reject unencrypted connections
    value = "1"
  }
}

resource "aws_db_instance" "main" {
  # checkov:skip=CKV_AWS_157: a Multi-AZ standby doubles the price; a go-live decision (see multi_az below)
  # checkov:skip=CKV_AWS_118: enhanced monitoring bills CloudWatch Logs per instance; basic metrics suffice for a micro instance
  # checkov:skip=CKV_AWS_353: Performance Insights is being folded into CloudWatch Database Insights (paid); revisit at go-live
  count = local.use_rds ? 1 : 0

  identifier     = var.project
  engine         = "postgres"
  engine_version = local.postgres_major # latest minor; minor upgrades applied in the maintenance window
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_user
  # RDS generates the password and keeps it in Secrets Manager (and rotates
  # it): it never appears in this code, the plan, or the state file.
  manage_master_user_password = true

  allocated_storage     = local.db_storage_gb
  max_allocated_storage = local.db_storage_max_gb
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  vpc_security_group_ids = [aws_security_group.db[0].id]
  parameter_group_name   = aws_db_parameter_group.main[0].name
  publicly_accessible    = false
  multi_az               = false # a standby doubles the price; a go-live decision

  backup_retention_period    = local.db_backup_retention
  copy_tags_to_snapshot      = true
  deletion_protection        = var.protect_from_deletion
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${var.project}-final"
  auto_minor_version_upgrade = true

  # Lets IAM roles log in with short-lived tokens instead of the password
  # (free). The app still uses the password; this is for people and tools.
  iam_database_authentication_enabled = true
  # Server logs (errors, slow queries) to CloudWatch, into the log group
  # below so they expire like the app's logs.
  enabled_cloudwatch_logs_exports = ["postgresql"]
  depends_on                      = [aws_cloudwatch_log_group.rds]
}

# RDS would create this group itself, with logs kept forever. Creating it
# first (same name) is how it gets a retention period.
# nosemgrep: terraform.aws.security.aws-cloudwatch-log-group-unencrypted.aws-cloudwatch-log-group-unencrypted - encrypted at rest by default; a customer KMS key is $1/month
resource "aws_cloudwatch_log_group" "rds" {
  # checkov:skip=CKV_AWS_158: CloudWatch encrypts logs at rest by default; a customer KMS key is $1/month
  # checkov:skip=CKV_AWS_338: 14-day retention is a deliberate cost guard (var.log_retention_days)
  count = local.use_rds ? 1 : 0

  name              = "/aws/rds/instance/${var.project}/postgresql"
  retention_in_days = var.log_retention_days
}

locals {
  db_host = local.use_rds ? aws_db_instance.main[0].address : var.db_host

  # The RDS-managed secret is JSON ({"username": ..., "password": ...});
  # ECS can inject one key of it with the ":password::" suffix.
  db_password_value_from = (local.use_rds
    ? "${aws_db_instance.main[0].master_user_secret[0].secret_arn}:password::"
    : "arn:aws:ssm:${var.region}:${local.account_id}:parameter${local.ssm_prefix}/${local.db_password_secret_name}"
  )
}

resource "aws_iam_role_policy" "execution_db_secret" {
  count = local.use_rds ? 1 : 0

  name = "read-rds-managed-password"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "ReadOnlyTheDatabasePassword"
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_db_instance.main[0].master_user_secret[0].secret_arn
    }]
  })
}
