output "function_name" {
  description = "The image variants Lambda, for `aws lambda invoke` or the console."
  value       = aws_lambda_function.image_variants.function_name
}

output "log_group" {
  description = "Its logs: aws logs tail <this> --follow"
  value       = aws_cloudwatch_log_group.image_variants.name
}

output "results_queue_url" {
  description = "Set as MEDIA_RESULTS_QUEUE_URL in the API's .env so it records variants."
  value       = aws_sqs_queue.results.url
}

output "dead_letter_queue_url" {
  description = "Uploads that failed every attempt; redrive with aws sqs start-message-move-task once fixed."
  value       = aws_sqs_queue.uploads_dlq.url
}
