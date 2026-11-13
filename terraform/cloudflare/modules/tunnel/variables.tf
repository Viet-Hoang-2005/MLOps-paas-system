variable "account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "tunnel_name" {
  description = "Name for the Cloudflare Zero Trust Tunnel"
  type        = string
  default     = "mlops-k3s-tunnel"
}

variable "domain_name" {
  description = "Root domain name (e.g. mlops-nids-nt114.id.vn)"
  type        = string
}

variable "tunnel_services" {
  description = "Map of subdomains and their backend cluster services routed through Cloudflare Tunnel"
  type = map(object({
    service       = string
    description   = optional(string, "")
    no_tls_verify = optional(bool, false)
  }))
  default = {}
}

