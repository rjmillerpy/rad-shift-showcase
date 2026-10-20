# S3 backend settings (item 16). The bucket is created by state-backend/.
bucket       = "radshift-tfstate-123456789012"
key          = "registry/terraform.tfstate"
region       = "us-east-2"
encrypt      = true
use_lockfile = true # S3-native locking (Terraform 1.10+); no DynamoDB table
