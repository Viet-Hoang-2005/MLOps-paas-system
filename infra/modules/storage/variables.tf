variable "enable_runtime_logs" {
  description = "Create the dedicated seven-day Loki log store with the K3s stack."
  type        = bool
  default     = false
}

variable "runtime_logs_bucket_name" {
  description = "Dedicated private Loki object-storage bucket."
  type        = string
  default     = "mlops-paas-runtime-logs"
}

variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
  default     = "mlops-paas-artifacts"
}

variable "cors_allowed_origins" {
  description = "Allowed origins for S3 bucket CORS"
  type        = list(string)
  default = [
    "https://mlops-nids-nt114.id.vn",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
  ]
}

variable "staging_expiration_days" {
  description = "Number of days before ephemeral staging uploads in S3 are automatically expired."
  type        = number
  default     = 1
}

variable "noncurrent_version_retention_days" {
  description = "Number of days to retain noncurrent object versions in the artifacts S3 bucket."
  type        = number
  default     = 30
}
