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
