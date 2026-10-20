# DNS and TLS for a real domain (roadmap item 14's go-live half). Nothing
# here exists until domain_name is set, so the default plan stays $0.
#
# At go-live: buy the domain (Route 53 Domains or any registrar, ~$15/year),
# which creates the hosted zone ($0.50/month); set domain_name; apply. ACM
# certificates for a load balancer are free and renew themselves.

data "aws_route53_zone" "main" {
  count = local.https_enabled ? 1 : 0

  name         = var.domain_name
  private_zone = false
}

locals {
  # Every name on the certificate; also what the DNS records are keyed by.
  certificate_names = local.https_enabled ? [var.domain_name, var.api_hostname] : []
}

# One certificate for the site and the API host.
resource "aws_acm_certificate" "main" {
  count = local.https_enabled ? 1 : 0

  domain_name               = local.certificate_names[0]
  subject_alternative_names = slice(local.certificate_names, 1, length(local.certificate_names))
  # DNS validation: ACM checks a CNAME in the zone, and keeps checking it to
  # renew, so renewal needs no one. (Email validation needs a person.)
  validation_method = "DNS"

  lifecycle {
    # A replaced certificate is issued before the old one is deleted, so the
    # listener is never without one.
    create_before_destroy = true

    precondition {
      condition     = endswith(var.api_hostname, ".${var.domain_name}")
      error_message = "api_hostname must be inside domain_name (e.g. api.example.com for example.com)."
    }
  }
}

# The CNAMEs ACM asked for, one per name on the certificate. Keyed by the
# names configured above, not by ACM's answer: that is only known after the
# certificate is requested, and for_each keys must be known at plan time.
resource "aws_route53_record" "certificate_validation" {
  for_each = toset(local.certificate_names)

  zone_id         = data.aws_route53_zone.main[0].zone_id
  name            = local.validation_options[each.key].resource_record_name
  type            = local.validation_options[each.key].resource_record_type
  records         = [local.validation_options[each.key].resource_record_value]
  ttl             = 300
  allow_overwrite = true # a re-created certificate asks for the same names
}

locals {
  validation_options = local.https_enabled ? {
    for option in aws_acm_certificate.main[0].domain_validation_options : option.domain_name => option
  } : {}
}

# Waits until ACM has issued the certificate; the HTTPS listener uses this.
resource "aws_acm_certificate_validation" "main" {
  count = local.https_enabled ? 1 : 0

  certificate_arn         = aws_acm_certificate.main[0].arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]
}

# The site and the API both point at the load balancer. Alias records are
# free to query and follow the ALB's changing addresses.
resource "aws_route53_record" "alb" {
  for_each = toset(local.certificate_names)

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = each.key
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
