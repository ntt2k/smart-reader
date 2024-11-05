output "bucket_name" {
  description = "Name of the created S3 bucket"
  value       = aws_s3_bucket.pdf_upload_bucket.id
}

output "bucket_arn" {
  description = "ARN of the created S3 bucket"
  value       = aws_s3_bucket.pdf_upload_bucket.arn
}

output "bucket_website_endpoint" {
  description = "S3 bucket website endpoint"
  value       = "https://${aws_s3_bucket.pdf_upload_bucket.bucket}.s3.${var.aws_region}.amazonaws.com"
}