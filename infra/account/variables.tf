variable "region" {
  description = "Region for the account-wide API calls (IAM and Budgets are global)."
  type        = string
  default     = "us-east-2"
}

variable "identity_center_region" {
  description = "The Region IAM Identity Center was enabled in."
  type        = string
  default     = "us-east-1"
}

variable "budget_alert_email" {
  description = "Who the budget alerts email. Set it in a gitignored *.auto.tfvars, not in the repo."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.budget_alert_email))
    error_message = "budget_alert_email must be an email address."
  }
}

variable "monthly_budgets_usd" {
  description = "Monthly cost budgets by name, in USD. Each emails at 80% and 100% of actual spend and when the forecast passes 100%."
  type        = map(number)
  default = {
    "radshift-monthly-5"  = 5
    "radshift-monthly-20" = 20
  }
}

variable "media_bucket_name" {
  description = "The bucket the app uploads media to (made by hand before Terraform; not managed here)."
  type        = string
  default     = "radshift-bucket"
}

variable "admin_user_name" {
  description = "The Identity Center user who gets AdministratorAccess."
  type        = string
  default     = "admin"
}
