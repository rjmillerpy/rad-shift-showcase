# Item 17: the container registry, applied now. The images outlive any
# cluster (and are what the local deploy runs today), so they get their own
# stack instead of living in the main stack, which stays unapplied until
# go-live. Costs pennies: see main.tf. See README.md in this directory.

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
