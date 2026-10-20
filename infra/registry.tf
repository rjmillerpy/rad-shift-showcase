# The image repositories are created by registry/ (item 17), which is applied
# now; this stack, applied at go-live, only looks them up. Images outlive any
# one cluster, and a `terraform destroy` here must not take them along.
data "aws_ecr_repository" "app" {
  for_each = local.container_ports

  name = "${var.project}-${each.key}"
}
