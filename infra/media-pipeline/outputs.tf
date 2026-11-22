output "function_name" {
  description = "The image variants Lambda, for `aws lambda invoke` or the console."
  value       = aws_lambda_function.image_variants.function_name
}

output "log_group" {
  description = "Its logs: aws logs tail <this> --follow"
  value       = aws_cloudwatch_log_group.image_variants.name
}
