# One Application Load Balancer for both services: requests for api_hostname
# go to the backend, everything else to the frontend. With a domain_name
# (dns.tf) it serves HTTPS and redirects HTTP; without one, plain HTTP.
# Cost at go-live: ~$16/month plus a public IPv4 per AZ (~$3.65 each).
# nosemgrep: terraform.aws.security.aws-elb-access-logs-not-enabled.aws-elb-access-logs-not-enabled - go-live decision (needs a log bucket); see the checkov:skip below
resource "aws_lb" "main" {
  # checkov:skip=CKV_AWS_91: access logs need an S3 log bucket and policy; added at go-live
  # checkov:skip=CKV2_AWS_28: WAF starts at ~$5/month plus per-rule fees; a go-live decision
  # checkov:skip=CKV2_AWS_20: aws_lb_listener.http redirects whenever domain_name is set; Checkov can't follow the condition
  name                       = var.project
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = [for subnet in aws_subnet.public : subnet.id]
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  idle_timeout               = 120 # Chronicle streams LLM output; give slow tokens room
  # A stray `terraform destroy` can't take the site down. Off only for
  # throwaway practice stacks (protect_from_deletion = false).
  enable_deletion_protection = var.protect_from_deletion
}

resource "aws_lb_target_group" "app" {
  # checkov:skip=CKV_AWS_378: TLS ends at the load balancer; ALB to task stays in the VPC and the task SG admits only the ALB
  for_each = local.container_ports

  name                 = "${var.project}-${each.key}"
  vpc_id               = aws_vpc.main.id
  target_type          = "ip" # required for Fargate (awsvpc networking)
  protocol             = "HTTP"
  port                 = each.value
  deregistration_delay = 30 # default 300 s makes every deploy wait five minutes

  health_check {
    path                = local.health_paths[each.key]
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  # checkov:skip=CKV_AWS_2: redirects to HTTPS whenever domain_name is set; plain HTTP only before a domain exists
  # checkov:skip=CKV_AWS_103: carries no TLS; the TLS policy is on aws_lb_listener.https
  load_balancer_arn = aws_lb.main.arn
  port              = local.http_port
  # nosemgrep: terraform.aws.security.insecure-load-balancer-tls-version.insecure-load-balancer-tls-version - plain HTTP only before a domain exists; redirects to HTTPS after
  protocol = "HTTP"

  # With a certificate: every request is redirected to HTTPS (permanent).
  dynamic "default_action" {
    for_each = local.https_enabled ? [1] : []
    content {
      type = "redirect"
      redirect {
        protocol    = "HTTPS"
        port        = tostring(local.https_port)
        status_code = "HTTP_301"
      }
    }
  }

  # Without one (no domain yet): serve the frontend over HTTP.
  dynamic "default_action" {
    for_each = local.https_enabled ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.app["frontend"].arn
    }
  }
}

resource "aws_lb_listener" "https" {
  count = local.https_enabled ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = local.https_port
  protocol          = "HTTPS"
  # TLS 1.3 and 1.2 only, forward-secret ciphers (AWS's current recommendation).
  # nosemgrep: terraform.aws.security.insecure-load-balancer-tls-version.insecure-load-balancer-tls-version - ELBSecurityPolicy-TLS13-1-2-Res-PQ-2025-09 is TLS 1.3/1.2 only; the rule doesn't know it
  ssl_policy = local.tls_policy
  # The validation resource, not the certificate: the listener waits until
  # ACM has actually issued it.
  certificate_arn = aws_acm_certificate_validation.main[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app["frontend"].arn
  }
}

resource "aws_lb_listener_rule" "api" {
  # On whichever listener serves traffic: HTTPS once there is a domain.
  listener_arn = local.https_enabled ? aws_lb_listener.https[0].arn : aws_lb_listener.http.arn
  priority     = 10

  condition {
    host_header {
      values = [var.api_hostname]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app["backend"].arn
  }
}
