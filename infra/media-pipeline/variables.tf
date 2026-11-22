variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "radshift"
}

variable "region" {
  description = "AWS region; the media bucket's own, so S3 can notify the function."
  type        = string
  default     = "us-east-2"
}

variable "media_bucket_name" {
  description = "The bucket the API uploads media to (made by hand before Terraform; looked up, not managed)."
  type        = string
  default     = "radshift-bucket"
}

variable "lambda_zip" {
  description = "The function's deployment zip, built by scripts/build_lambda.py."
  type        = string
  default     = "../../dist/image_variants.zip"
}

variable "source_prefix" {
  description = "Objects created under this prefix trigger the function. Must match lambdas/image_variants/constants.py."
  type        = string
  default     = "posts/"
}

variable "variant_prefix" {
  description = "Where the function writes. Must differ from source_prefix: writing under its own trigger would loop forever."
  type        = string
  default     = "variants/"

  validation {
    condition     = !startswith(var.variant_prefix, var.source_prefix) && !startswith(var.source_prefix, var.variant_prefix)
    error_message = "variant_prefix and source_prefix must not overlap, or every output re-triggers the function."
  }
}

variable "image_suffixes" {
  description = "Extensions that trigger the function (the API stores HEIC as .jpg)."
  type        = list(string)
  default     = [".jpg", ".jpeg", ".png", ".webp"]
}

variable "log_retention_days" {
  description = "Days the function's logs are kept. Short: they're for debugging, and storage is billed."
  type        = number
  default     = 14

  validation {
    condition     = var.log_retention_days >= 1 && var.log_retention_days <= 90
    error_message = "Keep logs between 1 and 90 days."
  }
}

variable "max_receive_count" {
  description = "Attempts per upload before it is parked in the dead-letter queue: the workflow's tries at a failing image, and the Pipe's at starting the workflow."
  type        = number
  default     = 3
}

variable "alert_email" {
  description = "Gets an email when an upload lands in the dead-letter queue (confirm the subscription email first). Set in media.auto.tfvars (gitignored); empty = no subscription."
  type        = string
  default     = ""
}

variable "app_user_name" {
  description = "The API's IAM user (infra/account/app_user.tf), which polls the results queue."
  type        = string
  default     = "radshift-app"
}
