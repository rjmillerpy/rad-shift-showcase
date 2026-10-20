# Item 13: the one part of the AWS setup that is applied for real now. IAM is
# free, so this stack costs $0. It is separate from the main stack in infra/
# (planned, never applied) so it can be applied on its own.
# See README.md in this directory.

terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69"
    }
  }

  # State lives in the S3 bucket from state-backend/ (item 16); the settings
  # are in backend.hcl: terraform init -backend-config=backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = var.project
      managed_by = "terraform"
    }
  }
}
