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

# Cấu hình vòng đời (Lifecycle) cho artifacts S3 bucket
resource "aws_s3_bucket_lifecycle_configuration" "artifacts_lifecycle" {
  bucket = aws_s3_bucket.artifacts_bucket.id

  # 1. Tự động dọn dẹp các object tạm thời trong staging (upload bỏ dở hoặc lưu thất bại)
  rule {
    id     = "ephemeral-staging-cleanup"
    status = "Enabled"

    filter {
      prefix = "staging/"
    }

    expiration {
      days = var.staging_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # 2. Quản lý phiên bản cũ (noncurrent versions) và delete marker cho toàn bộ bucket
  rule {
    id     = "artifacts-versioning-cleanup"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_retention_days
    }

    expiration {
      expired_object_delete_marker = true
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
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

# Dedicated Harbor container image storage (production only)
resource "aws_s3_bucket" "harbor_images" {
  count         = var.enable_harbor_images ? 1 : 0
  bucket        = var.harbor_images_bucket_name
  force_destroy = true
  tags          = { Component = "harbor-images" }
}

resource "aws_s3_bucket_ownership_controls" "harbor_images_acl_ownership" {
  count  = var.enable_harbor_images ? 1 : 0
  bucket = aws_s3_bucket.harbor_images[0].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "harbor_images" {
  count                   = var.enable_harbor_images ? 1 : 0
  bucket                  = aws_s3_bucket.harbor_images[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "harbor_images" {
  count  = var.enable_harbor_images ? 1 : 0
  bucket = aws_s3_bucket.harbor_images[0].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# Cleanup incomplete multipart uploads for harbor container images (e.g., interrupted pushes)
resource "aws_s3_bucket_lifecycle_configuration" "harbor_images" {
  count  = var.enable_harbor_images ? 1 : 0
  bucket = aws_s3_bucket.harbor_images[0].id
  rule {
    id     = "harbor-multipart-cleanup"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

