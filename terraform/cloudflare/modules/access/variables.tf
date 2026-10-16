variable "zone_id" {
  description = "Cloudflare Zone ID where the protected domain resides"
  type        = string
}

variable "applications" {
  description = "Map of applications to protect with Cloudflare Zero Trust Access (Email OTP)"
  type = map(object({
    name             = string
    domain           = string
    allowed_emails   = list(string)
    session_duration = optional(string, "24h")
  }))
  default = {}
}
