# Offline tests (mock AWS provider): pin the trust policy, the one thing that
# decides who can act in the account. Run: terraform test (from infra/github-oidc/).

mock_provider "aws" {
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
}

run "trusts_only_github_actions_through_the_oidc_provider" {
  command = plan

  assert {
    condition     = aws_iam_openid_connect_provider.github.url == "https://token.actions.githubusercontent.com"
    error_message = "The provider must be GitHub Actions' token issuer."
  }
  assert {
    condition     = aws_iam_openid_connect_provider.github.client_id_list == toset(["sts.amazonaws.com"])
    error_message = "The only accepted audience is STS."
  }
}

run "only_main_of_this_repository_can_assume_the_role" {
  assert {
    condition = jsondecode(aws_iam_role.github_deploy["backend"].assume_role_policy).Statement[0].Condition == {
      StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "repo:rjmillerpy/rad-shift:ref:refs/heads/main"
      }
    }
    error_message = "The trust policy must pin aud and sub exactly (StringEquals), with no other operator such as StringLike."
  }
  assert {
    condition     = jsondecode(aws_iam_role.github_deploy["backend"].assume_role_policy).Statement[0].Action == "sts:AssumeRoleWithWebIdentity"
    error_message = "OIDC roles are assumed with AssumeRoleWithWebIdentity only."
  }
  assert {
    condition     = jsondecode(aws_iam_role.github_deploy["backend"].assume_role_policy).Statement[0].Principal == { Federated = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
    error_message = "Only the GitHub OIDC provider may be trusted, not an account or a service."
  }
  assert {
    condition     = length(jsondecode(aws_iam_role.github_deploy["backend"].assume_role_policy).Statement) == 1
    error_message = "One trust statement; a second would be a second way in."
  }
}

run "each_repository_gets_its_own_role" {
  assert {
    condition     = aws_iam_role.github_deploy["backend"].name == "radshift-github-deploy"
    error_message = "The backend role keeps item 13's name, so its ARN (a repository variable) stays valid."
  }
  assert {
    condition     = jsondecode(aws_iam_role.github_deploy["frontend"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:rjmillerpy/rad-shift-frontend:ref:refs/heads/main"
    error_message = "The frontend role must trust only the frontend repository's main branch."
  }
  assert {
    condition     = length(jsondecode(aws_iam_role.github_deploy["frontend"].assume_role_policy).Statement) == 1
    error_message = "One trust statement per role: the frontend role must not also trust the backend repository."
  }
}

run "credentials_last_at_most_an_hour" {
  assert {
    condition     = alltrue([for role in aws_iam_role.github_deploy : role.max_session_duration == 3600])
    error_message = "Deploy credentials should expire within an hour."
  }
}

run "follows_a_different_branch_when_told" {
  variables {
    deploy_branch = "release"
  }
  assert {
    condition     = jsondecode(aws_iam_role.github_deploy["backend"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:rjmillerpy/rad-shift:ref:refs/heads/release"
    error_message = "The subject should follow deploy_branch."
  }
}

run "rejects_a_wildcard_repository" {
  command = plan
  variables {
    deploy_repositories = {
      backend = { repository = "rjmillerpy/*", role_name = "radshift-github-deploy" }
    }
  }
  expect_failures = [var.deploy_repositories]
}

run "rejects_a_wildcard_branch" {
  command = plan
  variables {
    deploy_branch = "*"
  }
  expect_failures = [var.deploy_branch]
}
