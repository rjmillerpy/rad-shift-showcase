# HTTPS mode (domain_name set): certificate, DNS and listeners, offline on a
# mock provider like main.tftest.hcl. Run: terraform test (from infra/).

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

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-2:123456789012:certificate/mock"
      # What ACM asks for: one CNAME per name on the certificate.
      domain_validation_options = [
        { domain_name = "test.example", resource_record_name = "_a.test.example.", resource_record_type = "CNAME", resource_record_value = "_a.acm-validations.aws." },
        { domain_name = "api.test.example", resource_record_name = "_b.api.test.example.", resource_record_type = "CNAME", resource_record_value = "_b.acm-validations.aws." },
      ]
    }
  }

  override_data {
    target = data.aws_route53_zone.main
    values = { zone_id = "Z0MOCK" }
  }

  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
}

variables {
  domain_name        = "test.example"
  api_hostname       = "api.test.example"
  app_url            = "https://test.example"
  backend_image_tag  = "test"
  frontend_image_tag = "test"
  db_host            = "db.test.internal"
  from_email         = "noreply@test.example"
}

run "http_redirects_to_https" {
  assert {
    condition     = one(aws_lb_listener.http.default_action).type == "redirect"
    error_message = "With a domain, port 80 must only redirect."
  }
  assert {
    condition = (
      one(one(aws_lb_listener.http.default_action).redirect).protocol == "HTTPS" &&
      one(one(aws_lb_listener.http.default_action).redirect).status_code == "HTTP_301"
    )
    error_message = "The redirect must be a permanent one to HTTPS."
  }
}

run "https_listener_uses_tls_1_2_or_newer" {
  assert {
    condition     = one(aws_lb_listener.https).ssl_policy == "ELBSecurityPolicy-TLS13-1-2-Res-PQ-2025-09"
    error_message = "TLS 1.3/1.2 only, with forward-secret ciphers."
  }
}

run "api_routing_moves_to_the_https_listener" {
  assert {
    condition     = aws_lb_listener_rule.api.listener_arn == one(aws_lb_listener.https).arn
    error_message = "Host routing must be on the listener that serves traffic."
  }
}

run "port_443_opens_only_in_https_mode" {
  assert {
    condition     = one(aws_vpc_security_group_ingress_rule.alb_https).from_port == 443
    error_message = "The ALB must accept HTTPS."
  }
}

run "certificate_covers_both_hosts_and_validates_by_dns" {
  assert {
    condition     = one(aws_acm_certificate.main).validation_method == "DNS"
    error_message = "DNS validation renews without a person; email validation doesn't."
  }
  assert {
    condition     = toset(keys(aws_route53_record.certificate_validation)) == toset(["test.example", "api.test.example"])
    error_message = "One validation record per name on the certificate."
  }
}

run "both_hosts_alias_the_load_balancer" {
  assert {
    condition     = toset(keys(aws_route53_record.alb)) == toset(["test.example", "api.test.example"])
    error_message = "The site and the API must both point at the ALB."
  }
  assert {
    condition     = alltrue([for record in aws_route53_record.alb : one(record.alias).name == aws_lb.main.dns_name])
    error_message = "Alias records, not CNAMEs to a fixed address."
  }
}

run "api_host_must_be_inside_the_domain" {
  command = plan
  variables { api_hostname = "api.other.example" }
  expect_failures = [aws_acm_certificate.main]
}
