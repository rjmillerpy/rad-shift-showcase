# Item 16: the account-level setup from item 9, made by hand in the console
# and CLI, now described as code and adopted with `import` blocks (applying
# them changes nothing in AWS; it only records the resources in state).
# Everything here is free. See README.md in this directory.

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

  # Only managed_by: these resources already carry project = "rad-shift",
  # and a default tag would fight the resource's own.
  default_tags {
    tags = { managed_by = "terraform" }
  }
}

# IAM Identity Center lives in us-east-1 (the Region it was enabled in).
provider "aws" {
  alias  = "identity_center"
  region = var.identity_center_region

  default_tags {
    tags = { managed_by = "terraform" }
  }
}
