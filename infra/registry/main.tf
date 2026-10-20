# One repository per image. Immutable tags: a tag (the commit SHA) always
# means the same image, so a deploy or rollback runs exactly what was tested.
# Basic scan-on-push is free.
#
# Cost: storage is $0.10/GB-month. Versions share their base layers, so ten
# of each image come to well under 1 GB (about 5-10 cents a month). Pushing
# is free; pulling to the local machine is internet egress, inside AWS's
# 100 GB/month free allowance (a deploy pulls only the changed layers).

resource "aws_ecr_repository" "app" {
  # checkov:skip=CKV_AWS_136: images are encrypted at rest with AES-256 by default; a customer KMS key is $1/month
  for_each = var.ci_roles

  name                 = "${var.project}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  # Destroying a repository that still holds images fails instead of
  # deleting every rollback target.
  force_delete = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each = aws_ecr_repository.app

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the ${var.images_kept} newest images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.images_kept
      }
      action = { type = "expire" }
    }]
  })
}
