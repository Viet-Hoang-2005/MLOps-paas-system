# S3 BUCKET
resource "aws_s3_bucket" "artifacts_bucket" {
  bucket        = var.bucket_name
  force_destroy = true
}

# Thiết lập quyền truy cập và versioning cho S3 bucket
resource "aws_s3_bucket_ownership_controls" "artifacts_acl_ownership" {
  bucket = aws_s3_bucket.artifacts_bucket.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Chặn truy cập công khai vào S3 bucket
resource "aws_s3_bucket_public_access_block" "artifacts_public_block" {
  bucket                  = aws_s3_bucket.artifacts_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Kích hoạt versioning cho S3 bucket
resource "aws_s3_bucket_versioning" "artifacts_versioning" {
  bucket = aws_s3_bucket.artifacts_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Cấu hình CORS cho S3 bucket (Hỗ trợ Presigned Upload)
resource "aws_s3_bucket_cors_configuration" "artifacts_cors" {
  bucket = aws_s3_bucket.artifacts_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD", "PUT", "POST"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket" "runtime_logs" {
  count         = var.enable_runtime_logs ? 1 : 0
  bucket        = var.runtime_logs_bucket_name
  force_destroy = true
  tags          = { Component = "runtime-logs" }
}

resource "aws_s3_bucket_public_access_block" "runtime_logs" {
  count                   = var.enable_runtime_logs ? 1 : 0
  bucket                  = aws_s3_bucket.runtime_logs[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "runtime_logs" {
  count  = var.enable_runtime_logs ? 1 : 0
  bucket = aws_s3_bucket.runtime_logs[0].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# Loki compactor implements the 168h retention. This is a cleanup safety net.
resource "aws_s3_bucket_lifecycle_configuration" "runtime_logs" {
  count  = var.enable_runtime_logs ? 1 : 0
  bucket = aws_s3_bucket.runtime_logs[0].id
  rule {
    id     = "runtime-log-expiration"
    status = "Enabled"
    filter {}
    expiration { days = 10 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

