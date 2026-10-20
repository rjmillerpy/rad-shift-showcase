# Offline tests: a mock AWS provider, so no credentials, no cost and nothing
# created. Each run pins a design decision that would be expensive or unsafe
# to lose. Run: terraform test (from infra/).

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

  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  # Mock data sources return random strings; the task definitions need a
  # URL-shaped value. (Both repositories get this one; tests check only the backend's.)
  mock_data "aws_ecr_repository" {
    defaults = { repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/radshift-backend" }
  }
}

variables {
  api_hostname       = "api.test.example"
  app_url            = "https://test.example"
  backend_image_tag  = "test"
  frontend_image_tag = "test"
  db_host            = "db.test.internal"
  from_email         = "noreply@test.example"
}

run "backend_never_runs_two_tasks" {
  assert {
    condition     = aws_ecs_service.backend.desired_count == 1
    error_message = "Two backend tasks would run the generator scheduler twice."
  }
  assert {
    condition     = aws_ecs_service.backend.deployment_maximum_percent == 100 && aws_ecs_service.backend.deployment_minimum_healthy_percent == 0
    error_message = "A deploy must stop the old backend task before starting the new one."
  }
}

run "rejects_a_second_backend_task" {
  command = plan
  variables { backend_desired_count = 2 }
  expect_failures = [var.backend_desired_count]
}

run "frontend_deploys_without_downtime" {
  assert {
    condition     = aws_ecs_service.frontend.deployment_minimum_healthy_percent == 100
    error_message = "The stateless frontend should start the new task before stopping the old one."
  }
}

run "secrets_come_from_ssm_never_plain_env" {
  # The expected names are written out here on purpose: comparing against
  # local.backend_secret_names would let a change to that list pass silently.
  assert {
    condition = toset([for s in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].secrets : s.name]) == toset(
      ["DB_PASSWORD", "JWT_SECRET", "RESEND_API_KEY", "ANTHROPIC_API_KEY", "ADMIN_SECRET"]
    )
    error_message = "The backend must receive exactly these secrets from SSM."
  }
  assert {
    condition = alltrue([
      for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment :
      !can(regex("(PASSWORD|SECRET|_KEY|TOKEN)$", e.name))
    ])
    error_message = "A secret-looking variable is passed as plain environment; move it to SSM."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].secrets :
      startswith(s.valueFrom, "arn:aws:ssm:us-east-2:123456789012:parameter/radshift/")
    ])
    error_message = "Every secret must be an SSM parameter under /radshift/."
  }
}

run "widget_execution_stays_off" {
  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : "${e.name}=${e.value}"],
      "WIDGET_SERVER_EXECUTION_ENABLED=false",
    )
    error_message = "The widget executor is not a sandbox; it must be disabled in ECS."
  }
}

run "backend_task_role_is_least_privilege" {
  assert {
    condition = toset(jsondecode(aws_iam_role_policy.backend_media.policy).Statement[0].Action) == toset(
      ["s3:PutObject", "s3:PutObjectAcl", "s3:GetObject", "s3:AbortMultipartUpload"]
    )
    error_message = "The backend task role should allow exactly the four S3 actions the app uses."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.backend_media.policy).Statement[0].Resource == "arn:aws:s3:::radshift-bucket/*"
    error_message = "The backend task role must be limited to objects in the media bucket."
  }
}

run "task_roles_trust_only_this_account" {
  assert {
    condition     = jsondecode(aws_iam_role.backend_task.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "123456789012"
    error_message = "The ECS trust policy needs the aws:SourceAccount condition."
  }
}

run "tasks_only_reachable_from_the_load_balancer" {
  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.tasks_from_alb :
      rule.referenced_security_group_id == aws_security_group.alb.id && rule.cidr_ipv4 == null
    ])
    error_message = "Task ingress must come only from the ALB security group, never a CIDR."
  }
}

run "internet_route_uses_the_free_gateway_not_nat" {
  assert {
    condition     = one(aws_route_table.public.route).gateway_id == aws_internet_gateway.main.id
    error_message = "The default route must use the internet gateway; a NAT gateway costs ~$36/month."
  }
  assert {
    condition     = alltrue([for subnet in aws_subnet.public : subnet.map_public_ip_on_launch == false])
    error_message = "Only tasks that ask for a public IP should get one."
  }
}

run "tasks_run_images_from_the_registry_stack" {
  assert {
    condition     = jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].image == "123456789012.dkr.ecr.us-east-2.amazonaws.com/radshift-backend:test"
    error_message = "The backend task must run the tagged image from registry/'s repository."
  }
  assert {
    condition     = toset([for repo in data.aws_ecr_repository.app : repo.name]) == toset(["radshift-backend", "radshift-frontend"])
    error_message = "Look up the repositories registry/ creates, by name."
  }
}

run "cost_guards" {
  assert {
    condition     = alltrue([for group in aws_cloudwatch_log_group.app : group.retention_in_days == 14])
    error_message = "Logs need a retention period; CloudWatch bills for storage forever otherwise."
  }
  assert {
    condition     = one([for s in aws_ecs_cluster.main.setting : s.value if s.name == "containerInsights"]) == "disabled"
    error_message = "Container Insights is billed per metric; the ALB's free metrics drive the alarms (monitoring.tf)."
  }
  assert {
    condition     = one(aws_ecs_service.backend.capacity_provider_strategy).capacity_provider == "FARGATE_SPOT"
    error_message = "Default to Fargate Spot (~70% cheaper) for the demo."
  }
}

run "api_host_routes_to_the_backend" {
  assert {
    condition     = one(one(aws_lb_listener_rule.api.condition).host_header).values == toset(["api.test.example"])
    error_message = "Requests for api_hostname must go to the backend."
  }
  assert {
    condition     = one(aws_lb_listener.http.default_action).target_group_arn == aws_lb_target_group.app["frontend"].arn
    error_message = "Everything else must go to the frontend."
  }
}

run "deploy_role_reaches_only_this_apps_resources" {
  assert {
    condition     = aws_iam_role_policy.github_deploy.role == "radshift-github-deploy"
    error_message = "The deploy policy belongs on the role from infra/github-oidc/."
  }
  assert {
    condition = toset(flatten([
      for s in jsondecode(aws_iam_role_policy.github_deploy.policy).Statement : s.Action if s.Resource == "*"
    ])) == toset(["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"])
    error_message = "Only actions AWS can't scope to a resource may use Resource \"*\"."
  }
  assert {
    condition = !anytrue([
      for s in jsondecode(aws_iam_role_policy.github_deploy.policy).Statement : anytrue([for a in flatten([s.Action]) : startswith(a, "ecr:")])
    ])
    error_message = "Image access belongs to registry/, which owns the repositories; this policy only deploys."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.github_deploy.policy).Statement :
      s.Condition.StringEquals["iam:PassedToService"] == "ecs-tasks.amazonaws.com" if contains(flatten([s.Action]), "iam:PassRole")
    ])
    error_message = "iam:PassRole must be limited to ECS tasks."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.github_deploy.policy).Statement : s.Effect == "Allow" && !anytrue([
        for a in flatten([s.Action]) : endswith(a, "*")
      ])
    ])
    error_message = "No wildcard actions in the deploy policy."
  }
}

run "backend_trusts_forwarded_headers_only_from_the_vpc" {
  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : "${e.name}=${e.value}"],
      "FORWARDED_ALLOW_IPS=10.20.0.0/16",
    )
    error_message = "Behind the ALB, uvicorn must trust X-Forwarded-For from the VPC (never \"*\"), or every client looks like the load balancer."
  }
}

run "metrics_endpoint_is_off_on_aws" {
  assert {
    condition     = one([for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.value if e.name == "METRICS_ENABLED"]) == "false"
    error_message = "Nothing scrapes /metrics on AWS; the route must not exist there (app/metrics/service.py)."
  }
}

run "alarms_page_through_sns" {
  assert {
    condition = alltrue([
      for alarm in [aws_cloudwatch_metric_alarm.backend_error_rate, aws_cloudwatch_metric_alarm.backend_unhealthy] :
      alarm.alarm_actions == toset([aws_sns_topic.alerts.arn]) && alarm.ok_actions == toset([aws_sns_topic.alerts.arn])
    ])
    error_message = "Both alarms must notify when they fire and when they recover."
  }
  assert {
    condition     = length(aws_sns_topic_subscription.alert_email) == 0
    error_message = "No alert_email, no subscription (AWS would email a confirmation to nobody)."
  }
}

run "error_rate_alarm_matches_the_prometheus_rule" {
  assert {
    condition     = aws_cloudwatch_metric_alarm.backend_error_rate.threshold == 5 && aws_cloudwatch_metric_alarm.backend_error_rate.evaluation_periods == 5
    error_message = "Above 5% for 5 minutes, as HighServerErrorRate in observability/prometheus/alerts.yml."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.backend_error_rate.treat_missing_data == "notBreaching"
    error_message = "No traffic is not an outage; the unhealthy-host alarm covers a dead backend."
  }
  assert {
    condition = toset([
      for q in aws_cloudwatch_metric_alarm.backend_error_rate.metric_query : one(q.metric).metric_name if length(q.metric) > 0
    ]) == toset(["HTTPCode_Target_5XX_Count", "RequestCount"])
    error_message = "The rate is the target's own 5xx over all its requests."
  }
}

run "unhealthy_backend_alarm_treats_silence_as_down" {
  assert {
    condition     = aws_cloudwatch_metric_alarm.backend_unhealthy.treat_missing_data == "breaching"
    error_message = "A target group reporting nothing has no healthy backend either."
  }
}

run "alert_email_subscribes_when_set" {
  variables {
    alert_email = "oncall@test.example"
  }
  assert {
    condition     = one(aws_sns_topic_subscription.alert_email).endpoint == "oncall@test.example" && one(aws_sns_topic_subscription.alert_email).protocol == "email"
    error_message = "alert_email must get an email subscription to the alerts topic."
  }
}

run "http_only_without_a_domain" {
  assert {
    condition     = one(aws_lb_listener.http.default_action).type == "forward" && length(aws_lb_listener.https) == 0
    error_message = "No domain: serve HTTP, create no HTTPS listener."
  }
  assert {
    condition     = length(aws_acm_certificate.main) == 0 && length(aws_route53_record.alb) == 0 && length(aws_vpc_security_group_ingress_rule.alb_https) == 0
    error_message = "No domain: no certificate, DNS records or port 443 (all would fail without a zone)."
  }
}

run "default_security_group_allows_nothing" {
  assert {
    condition     = length(aws_default_security_group.main.ingress) == 0 && length(aws_default_security_group.main.egress) == 0
    error_message = "The VPC's default security group must have no rules."
  }
}

run "load_balancer_protected_from_deletion" {
  assert {
    condition     = aws_lb.main.enable_deletion_protection
    error_message = "Deletion protection is on unless deliberately turned off."
  }
}
