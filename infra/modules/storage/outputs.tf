output "runtime_logs_bucket_arn" {
  value = var.enable_runtime_logs ? aws_s3_bucket.runtime_logs[0].arn : ""
}

output "runtime_logs_bucket_name" {
  value = var.enable_runtime_logs ? aws_s3_bucket.runtime_logs[0].id : null
}

output "bucket_id" {
  description = "The name of the bucket"
  value       = aws_s3_bucket.artifacts_bucket.id
}

output "bucket_arn" {
  description = "The ARN of the bucket"
  value       = aws_s3_bucket.artifacts_bucket.arn
}
