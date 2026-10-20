resource "aws_ecs_cluster" "main" {
  # checkov:skip=CKV_AWS_65: Container Insights bills per metric; the alarms use the ALB's free metrics (monitoring.tf)
  name = var.project

  # Container Insights bills per metric; the ALB's free metrics drive the
  # alarms instead (monitoring.tf, item 15).
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

locals {
  capacity_provider = var.use_fargate_spot ? "FARGATE_SPOT" : "FARGATE"

  backend_environment = {
    DB_HOST                         = local.db_host
    DB_PORT                         = "5432"
    DB_NAME                         = var.db_name
    DB_USER                         = var.db_user
    ALLOWED_ORIGINS                 = var.app_url
    APP_URL                         = var.app_url
    FROM_EMAIL                      = var.from_email
    S3_BUCKET_NAME                  = var.media_bucket_name
    S3_EXPECTED_BUCKET_OWNER        = local.account_id # S3 refuses the bucket if another account owns it
    AWS_DEFAULT_REGION              = var.region
    WIDGET_SERVER_EXECUTION_ENABLED = "false" # the executor is not a sandbox
    METRICS_ENABLED                 = "false" # no /metrics route: CloudWatch reads the ALB (monitoring.tf)
    # uvicorn trusts X-Forwarded-For/-Proto only from these addresses. The ALB's
    # nodes sit in this VPC's public subnets, and the task security group only
    # admits the ALB, so nothing else in the range can reach the task.
    FORWARDED_ALLOW_IPS = var.vpc_cidr
  }

  log_options = {
    for name in keys(local.container_ports) : name => {
      "awslogs-group"         = aws_cloudwatch_log_group.app[name].name
      "awslogs-region"        = var.region
      "awslogs-stream-prefix" = name
    }
  }
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.backend_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64" # images are built amd64 in CI; ARM is ~20% cheaper if CI builds arm64
  }

  container_definitions = jsonencode([{
    name         = "backend"
    image        = "${data.aws_ecr_repository.app["backend"].repository_url}:${var.backend_image_tag}"
    essential    = true
    portMappings = [{ containerPort = local.container_ports.backend, protocol = "tcp" }]
    environment  = [for name, value in local.backend_environment : { name = name, value = value }]
    secrets = concat(
      [for name in local.backend_ssm_secret_names : {
        name      = name
        valueFrom = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${local.ssm_prefix}/${name}"
      }],
      [{ name = local.db_password_secret_name, valueFrom = local.db_password_value_from }],
    )
    logConfiguration = { logDriver = "awslogs", options = local.log_options.backend }
    # Same check as compose.yaml: /health pings the database.
    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:${local.container_ports.backend}${local.health_paths.backend}')"]
      interval    = 10
      timeout     = 5
      retries     = 3
      startPeriod = 60 # the entrypoint runs migrations before uvicorn starts
    }
    stopTimeout = 30
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.project}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.frontend_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name             = "frontend"
    image            = "${data.aws_ecr_repository.app["frontend"].repository_url}:${var.frontend_image_tag}"
    essential        = true
    portMappings     = [{ containerPort = local.container_ports.frontend, protocol = "tcp" }]
    logConfiguration = { logDriver = "awslogs", options = local.log_options.frontend }
    healthCheck = {
      command     = ["CMD", "/nodejs/bin/node", "-e", "fetch('http://127.0.0.1:${local.container_ports.frontend}${local.health_paths.frontend}').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
      interval    = 10
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

resource "aws_ecs_service" "backend" {
  # checkov:skip=CKV_AWS_333: no NAT gateway (~$36/month), so tasks need a public IP to reach ECR and APIs; the SG admits only the ALB
  name                              = "backend"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.backend.arn
  desired_count                     = var.backend_desired_count
  health_check_grace_period_seconds = 90
  propagate_tags                    = "SERVICE"

  # Never two backend tasks at once, not even during a deploy: each one starts
  # the generator scheduler. The old task stops before the new one starts, so
  # a deploy has a short outage. Splitting the scheduler out removes this.
  deployment_maximum_percent         = 100
  deployment_minimum_healthy_percent = 0

  deployment_circuit_breaker {
    enable   = true
    rollback = true # a release that never gets healthy rolls back by itself
  }

  capacity_provider_strategy {
    capacity_provider = local.capacity_provider
    weight            = 1
  }

  network_configuration {
    subnets          = [for subnet in aws_subnet.public : subnet.id]
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true # no NAT gateway; see network.tf
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app["backend"].arn
    container_name   = "backend"
    container_port   = local.container_ports.backend
  }

  depends_on = [aws_lb_listener_rule.api]
}

resource "aws_ecs_service" "frontend" {
  # checkov:skip=CKV_AWS_333: no NAT gateway (~$36/month), so tasks need a public IP to reach ECR; the SG admits only the ALB
  name                              = "frontend"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.frontend.arn
  desired_count                     = 1
  health_check_grace_period_seconds = 30
  propagate_tags                    = "SERVICE"

  # Stateless: start the new task before stopping the old one (no outage).
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  capacity_provider_strategy {
    capacity_provider = local.capacity_provider
    weight            = 1
  }

  network_configuration {
    subnets          = [for subnet in aws_subnet.public : subnet.id]
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app["frontend"].arn
    container_name   = "frontend"
    container_port   = local.container_ports.frontend
  }

  depends_on = [aws_lb_listener.http]
}
