# A VPC with two public subnets and no NAT gateway. Tasks get public IPs so
# they can pull images and call S3, Anthropic and Resend directly; security
# groups keep them reachable only from the load balancer. A NAT gateway would
# add ~$36/month; VPC endpoints ~$7/month each. Both are go-live decisions.

locals {
  public_subnets = {
    for index, az in var.availability_zones :
    az => cidrsubnet(var.vpc_cidr, 8, index)
  }
}

resource "aws_vpc" "main" {
  # checkov:skip=CKV2_AWS_11: flow logs bill per GB ingested; turn on (to S3, the cheap target) at go-live
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.project }
}

# Every VPC comes with a default security group whose members may all talk
# to each other. Nothing here uses it; managing it with no rules empties it,
# so anything placed in it by mistake gets no traffic at all.
resource "aws_default_security_group" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project}-default-unused" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = var.project }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false # tasks ask for one explicitly; nothing else should get one

  tags = { Name = "${var.project}-public-${each.key}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.project}-public" }
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "alb" {
  name        = "${var.project}-alb"
  description = "Load balancer: HTTP and HTTPS from the internet"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  # checkov:skip=CKV_AWS_260: a public site must accept port 80, if only to redirect it to HTTPS
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from anywhere"
  ip_protocol       = "tcp"
  from_port         = local.http_port
  to_port           = local.http_port
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  count = local.https_enabled ? 1 : 0

  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from anywhere"
  ip_protocol       = "tcp"
  from_port         = local.https_port
  to_port           = local.https_port
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  for_each = local.container_ports

  security_group_id            = aws_security_group.alb.id
  description                  = "To the ${each.key} tasks"
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  referenced_security_group_id = aws_security_group.tasks.id
}

resource "aws_security_group" "tasks" {
  name        = "${var.project}-tasks"
  description = "ECS tasks: reachable only from the load balancer"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  for_each = local.container_ports

  security_group_id            = aws_security_group.tasks.id
  description                  = "${each.key} port from the load balancer only"
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "tasks_out" {
  security_group_id = aws_security_group.tasks.id
  description       = "All outbound: ECR, S3, Anthropic, Resend and the database"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
