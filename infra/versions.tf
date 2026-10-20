# Item 10 (ECS Fargate), written in $0 mode: validated, tested and planned
# against the real account, never applied until the app goes live.
# See infra/README.md.

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

data "aws_caller_identity" "current" {}
