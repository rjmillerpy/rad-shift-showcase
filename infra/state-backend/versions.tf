# Item 16: the S3 bucket that holds every other stack's Terraform state.
# Costs pennies: state files are kilobytes (S3 Standard is $0.023/GB-month,
# plus fractions of a cent in requests). See README.md in this directory.

terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69"
    }
  }

  # This stack's own state stays local (gitignored): the bucket can't hold
  # the state of the stack that creates it. If the file is lost, nothing
  # breaks; `terraform import` the bucket (README.md) and carry on.
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
