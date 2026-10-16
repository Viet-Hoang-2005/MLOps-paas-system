variable "zone_id" {
  description = "Cloudflare Zone ID to apply security settings to"
  type        = string
}

variable "ssl_mode" {
  description = "SSL Encryption mode (off, flexible, full, strict)"
  type        = string
  default     = "strict"
}

variable "min_tls_version" {
  description = "Minimum TLS version allowed"
  type        = string
  default     = "1.2"
}

