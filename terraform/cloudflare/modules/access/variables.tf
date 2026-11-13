variable "account_id" {
  description = "Cloudflare Account ID where Zero Trust Access is managed"
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
