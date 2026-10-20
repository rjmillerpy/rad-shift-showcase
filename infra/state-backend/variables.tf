variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "radshift"
}

variable "region" {
  description = "Region for the state bucket; the same as the main stack's (us-east-2)."
  type        = string
  default     = "us-east-2"
}

variable "noncurrent_version_days" {
  description = "How long old versions of a state file are kept. Each one is a restore point after a bad apply or a corrupted state."
  type        = number
  default     = 90
}
