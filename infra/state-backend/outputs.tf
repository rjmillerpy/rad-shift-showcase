output "bucket" {
  description = "The state bucket; each stack's backend.hcl names it."
  value       = aws_s3_bucket.state.bucket
}

output "region" {
  description = "The bucket's region, for backend.hcl."
  value       = var.region
}
