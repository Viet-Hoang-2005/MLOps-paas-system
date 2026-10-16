variable "zone_id" {
  description = "Cloudflare Zone ID for the domain"
  type        = string
}

variable "domain_name" {
  description = "Root domain name (e.g. mlops-nids-nt114.id.vn)"
  type        = string
}

variable "alb_dns_name" {
  description = "AWS ALB DNS name for direct ingress (api and registry)"
  type        = string
}

variable "acm_validation_records" {
  description = "List of ACM domain validation records exported from AWS Terraform"
  type = list(object({
    name   = string
    record = string
    type   = string
  }))
  default = []
}

variable "api_proxied" {
  description = "Whether the api subdomain should be proxied by Cloudflare CDN"
  type        = bool
  default     = false
}

variable "tunnel_id" {
  description = "Cloudflare Zero Trust Tunnel ID"
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

