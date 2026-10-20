# Item 11: the two database modes. Mirrors database.tf.

mock_provider "aws" {
  # Mocks invent random strings for computed values; the provider validates
  # ARN-shaped arguments, so give the ones that feed other resources a real shape.
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:loadbalancer/app/mock/1" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:targetgroup/mock/1" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/mock/1/1" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-2:123456789012:task-definition/mock:1" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-2:123456789012:mock" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { id = "arn:aws:ecs:us-east-2:123456789012:cluster/mock", arn = "arn:aws:ecs:us-east-2:123456789012:cluster/mock" }
  }

  # master_user_secret is computed by RDS; give the mock a realistic value.
  mock_resource "aws_db_instance" {
    defaults = {
      address = "radshift.abc123.us-east-2.rds.amazonaws.com"
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:us-east-2:123456789012:secret:rds!db-mock"
        kms_key_id    = "arn:aws:kms:us-east-2:123456789012:key/mock"
        secret_status = "active"
      }]
    }
  }

  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
}

variables {
  api_hostname       = "api.test.example"
  app_url            = "https://test.example"
  backend_image_tag  = "test"
  frontend_image_tag = "test"
  from_email         = "noreply@test.example"
}

run "external_mode_creates_no_database" {
  variables { db_host = "ep-mock.us-east-2.aws.neon.tech" }

  assert {
    condition     = length(aws_db_instance.main) == 0 && length(aws_security_group.db) == 0
    error_message = "External mode must not create an RDS instance."
  }
  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : "${e.name}=${e.value}"],
      "DB_HOST=ep-mock.us-east-2.aws.neon.tech",
    )
    error_message = "External mode must connect to db_host."
  }
  assert {
    condition = one([
      for s in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].secrets : s.valueFrom if s.name == "DB_PASSWORD"
    ]) == "arn:aws:ssm:us-east-2:123456789012:parameter/radshift/DB_PASSWORD"
    error_message = "External mode reads the database password from SSM."
  }
}

run "external_mode_requires_a_host" {
  command         = plan
  expect_failures = [var.db_host]
}

run "rds_is_private_encrypted_and_backed_up" {
  variables { database_mode = "rds" }

  assert {
    condition     = aws_db_instance.main[0].publicly_accessible == false
    error_message = "The database must not be reachable from the internet."
  }
  assert {
    condition     = toset(aws_db_subnet_group.main[0].subnet_ids) == toset([for s in aws_subnet.private : s.id])
    error_message = "The database must live in the private subnets."
  }
  assert {
    condition     = aws_db_instance.main[0].storage_encrypted && aws_db_instance.main[0].backup_retention_period == 7
    error_message = "Storage must be encrypted and backed up for 7 days."
  }
  assert {
    condition     = aws_db_instance.main[0].deletion_protection && aws_db_instance.main[0].skip_final_snapshot == false
    error_message = "Deleting the database must be blocked, and must leave a final snapshot."
  }
  assert {
    condition     = one([for p in aws_db_parameter_group.main[0].parameter : p.value if p.name == "rds.force_ssl"]) == "1"
    error_message = "The database must reject unencrypted connections."
  }
}

run "rds_password_never_in_terraform" {
  variables { database_mode = "rds" }

  assert {
    condition     = aws_db_instance.main[0].manage_master_user_password && aws_db_instance.main[0].password == null
    error_message = "RDS must generate and keep the password; Terraform must never set it."
  }
  assert {
    condition = one([
      for s in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].secrets : s.valueFrom if s.name == "DB_PASSWORD"
    ]) == "arn:aws:secretsmanager:us-east-2:123456789012:secret:rds!db-mock:password::"
    error_message = "The backend must read DB_PASSWORD from the RDS-managed secret's password key."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.execution_db_secret[0].policy).Statement[0].Resource == "arn:aws:secretsmanager:us-east-2:123456789012:secret:rds!db-mock"
    error_message = "The execution role may read only the database's own secret."
  }
}

run "rds_only_reachable_from_the_tasks" {
  variables { database_mode = "rds" }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.db_from_tasks[0].referenced_security_group_id == aws_security_group.tasks.id
    error_message = "Postgres must accept connections only from the ECS tasks."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.db_from_tasks[0].cidr_ipv4 == null
    error_message = "No CIDR may reach the database."
  }
  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : "${e.name}=${e.value}"],
      "DB_HOST=radshift.abc123.us-east-2.rds.amazonaws.com",
    )
    error_message = "In rds mode the backend must connect to the RDS address."
  }
}

run "rds_logs_expire_and_iam_login_is_available" {
  variables { database_mode = "rds" }

  assert {
    condition     = one(aws_db_instance.main).enabled_cloudwatch_logs_exports == toset(["postgresql"])
    error_message = "Postgres server logs go to CloudWatch."
  }
  assert {
    condition     = one(aws_cloudwatch_log_group.rds).name == "/aws/rds/instance/radshift/postgresql" && one(aws_cloudwatch_log_group.rds).retention_in_days == 14
    error_message = "The group RDS writes to must exist first, with a retention period (RDS's own keeps logs forever)."
  }
  assert {
    condition     = one(aws_db_instance.main).iam_database_authentication_enabled
    error_message = "IAM database authentication lets people log in without the password."
  }
}
