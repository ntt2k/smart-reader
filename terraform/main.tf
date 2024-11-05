resource "aws_s3_bucket" "pdf_upload_bucket" {
  bucket = var.bucket_name

  tags = {
    Name = "PDF Upload Bucket"
  }
}

resource "aws_s3_bucket_cors_configuration" "pdf_bucket_cors" {
  bucket = aws_s3_bucket.pdf_upload_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "POST", "PUT"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_public_access_block" "pdf_bucket_public_access_block" {
  bucket = aws_s3_bucket.pdf_upload_bucket.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "pdf_bucket_policy" {
  bucket = aws_s3_bucket.pdf_upload_bucket.id
  policy = data.aws_iam_policy_document.bucket_policy.json
}

data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid    = "PublicReadAccess"
    effect = "Allow"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.pdf_upload_bucket.arn,
      "${aws_s3_bucket.pdf_upload_bucket.arn}/*"
    ]
  }
}