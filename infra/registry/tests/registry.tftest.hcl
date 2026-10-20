# Offline tests (mock AWS provider): pin who can push what, and the settings
# that make a rollback possible. Run: terraform test (from infra/registry/).

mock_provider "aws" {
  # Each repository needs its own ARN, or "the frontend role can't touch the
  # backend repository" couldn't be told apart from the opposite.
  override_resource {
    target = aws_ecr_repository.app["backend"]
    values = {
      arn            = "arn:aws:ecr:us-east-2:123456789012:repository/radshift-backend"
      repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/radshift-backend"
    }
  }
  override_resource {
    target = aws_ecr_repository.app["frontend"]
    values = {
      arn            = "arn:aws:ecr:us-east-2:123456789012:repository/radshift-frontend"
      repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/radshift-frontend"
    }
  }
}

variables {
  backend_arn  = "arn:aws:ecr:us-east-2:123456789012:repository/radshift-backend"
  frontend_arn = "arn:aws:ecr:us-east-2:123456789012:repository/radshift-frontend"
}

run "tags_are_immutable_and_images_scanned" {
  command = plan

  assert {
    condition = alltrue([
      for repo in aws_ecr_repository.app :
      repo.image_tag_mutability == "IMMUTABLE" && repo.image_scanning_configuration[0].scan_on_push
    ])
    error_message = "A tag must always mean the same image, and every image is scanned on push."
  }
  assert {
    condition     = alltrue([for repo in aws_ecr_repository.app : repo.force_delete == false])
    error_message = "Destroying a repository must not silently delete every rollback target."
  }
  assert {
    condition     = toset([for repo in aws_ecr_repository.app : repo.name]) == toset(["radshift-backend", "radshift-frontend"])
    error_message = "The main stack looks the repositories up by these names."
  }
}

run "keeps_enough_images_to_roll_back" {
  command = plan

  assert {
    condition = alltrue([
      for policy in aws_ecr_lifecycle_policy.app :
      jsondecode(policy.policy).rules[0].selection.countNumber == 10
    ])
    error_message = "Keep the 10 newest images of each component."
  }
}

run "rejects_keeping_a_single_image" {
  command = plan
  variables {
    images_kept = 1
  }
  expect_failures = [var.images_kept]
}

run "each_role_pushes_only_its_own_image" {
  assert {
    condition = one([
      for s in jsondecode(aws_iam_role_policy.ci["frontend"].policy).Statement : s.Resource if s.Sid == "PushOwnImage"
    ]) == var.frontend_arn
    error_message = "The frontend role may push only to the frontend repository."
  }
  assert {
    condition = one([
      for s in jsondecode(aws_iam_role_policy.ci["backend"].policy).Statement : s.Resource if s.Sid == "PushOwnImage"
    ]) == var.backend_arn
    error_message = "The backend role may push only to the backend repository."
  }
  assert {
    condition = !anytrue([
      for s in jsondecode(aws_iam_role_policy.ci["frontend"].policy).Statement : contains(flatten([s.Resource]), var.backend_arn)
    ])
    error_message = "The frontend role must not reach the backend repository at all."
  }
  assert {
    condition     = aws_iam_role_policy.ci["frontend"].role == "radshift-frontend-github-deploy" && aws_iam_role_policy.ci["backend"].role == "radshift-github-deploy"
    error_message = "Each policy belongs on its repository's role from github-oidc/."
  }
}

run "only_the_deploying_repository_pulls_every_image" {
  assert {
    condition = toset(flatten([
      for s in jsondecode(aws_iam_role_policy.ci["backend"].policy).Statement : s.Resource if s.Sid == "PullEveryImageToDeploy"
    ])) == toset([var.backend_arn, var.frontend_arn])
    error_message = "The deploy workflow (backend repository) must be able to pull both images."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.ci["backend"].policy).Statement :
      !contains(flatten([s.Action]), "ecr:PutImage") if s.Sid == "PullEveryImageToDeploy"
    ])
    error_message = "Pulling every image must not come with pushing to every repository."
  }
  assert {
    condition     = length([for s in jsondecode(aws_iam_role_policy.ci["frontend"].policy).Statement : s if s.Sid == "PullEveryImageToDeploy"]) == 0
    error_message = "The frontend repository doesn't deploy, so it pulls nothing else."
  }
}

run "no_wildcards_beyond_what_aws_requires" {
  assert {
    condition = alltrue([
      for policy in aws_iam_role_policy.ci : toset(flatten([
        for s in jsondecode(policy.policy).Statement : s.Action if s.Resource == "*"
      ])) == toset(["ecr:GetAuthorizationToken"])
    ])
    error_message = "Only ecr:GetAuthorizationToken, which AWS can't scope to a repository, may use Resource \"*\"."
  }
  assert {
    condition = alltrue(flatten([
      for policy in aws_iam_role_policy.ci : [
        for s in jsondecode(policy.policy).Statement : s.Effect == "Allow" && !anytrue([for a in flatten([s.Action]) : endswith(a, "*")])
      ]
    ]))
    error_message = "No wildcard actions."
  }
}
