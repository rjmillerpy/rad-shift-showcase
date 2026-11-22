# Phase 5 (items 27-29): the media pipeline, applied now. Lambda, SQS, SNS
# and Step Functions all fit AWS's always-free monthly allowances at this
# app's volume, so this stack runs for real instead of waiting for go-live
# like the main stack. See README.md in this directory for the cost.

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
