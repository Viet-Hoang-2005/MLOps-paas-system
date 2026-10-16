# Cloudflare Authentication & Account Variables
variable "cloudflare_api_token" {
  description = "Cloudflare API Token with Zone (DNS:Edit, Zone Settings:Edit) and Account (Cloudflare Tunnel:Edit) permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID (found on the right sidebar of the Cloudflare Dashboard)"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for the target domain (found in the domain Overview page)"
  type        = string
}

variable "domain_name" {
  description = "Root domain name managed on Cloudflare"
  type        = string
  default     = "mlops-nids-nt114.id.vn"
}

# Data Linkage from AWS Terraform
variable "alb_dns_name" {
  description = "DNS name of the AWS Application Load Balancer"
  type        = string
  default     = ""
}

variable "acm_validation_records" {
  description = "ACM SSL Certificate validation records"
  type = list(object({
    name   = string
    record = string
    type   = string
  }))
  default = []
}

variable "api_proxied" {
  description = "Whether to proxy api.domain through Cloudflare CDN (default: false for direct ALB connectivity, large payloads, and long timeouts)"
  type        = bool
  default     = false
}

# Cloudflare Zero Trust Tunnel Configuration
variable "tunnel_name" {
  description = "Name for the Cloudflare Zero Trust Tunnel connector"
  type        = string
  default     = "mlops-k3s-tunnel"
}

variable "tunnel_services" {
  description = "Map of subdomains and internal cluster service endpoints exposed securely through Cloudflare Zero Trust Tunnel"
  type = map(object({
    service       = string
    description   = optional(string, "")
    no_tls_verify = optional(bool, false)
  }))
  default = {
    "@" = {
      service     = "http://mlops-paas-web.mlops-web.svc.cluster.local:80"
      description = "MLOps PaaS Web Dashboard"
    }
    "argocd" = {
      service       = "https://argocd-server.argocd.svc.cluster.local:443"
      description   = "Argo CD GitOps Dashboard"
      no_tls_verify = true
    }
    "workflow" = {
      service     = "http://argo-workflows-server.argo.svc.cluster.local:2746"
      description = "Argo Workflows UI"
    }
    "grafana" = {
      service     = "http://monitoring-grafana.monitoring.svc.cluster.local:80"
      description = "Grafana Monitoring Dashboard"
    }
    "headlamp" = {
      service     = "http://headlamp.headlamp.svc.cluster.local:80"
      description = "Kubernetes Web UI Headlamp"
    }
  }
}

# Zone Security & Optimization Settings
variable "ssl_mode" {
  description = "SSL Encryption mode between Cloudflare and Origin (strict, full, flexible, off). Default is strict."
  type        = string
  default     = "strict"
}

variable "min_tls_version" {
  description = "Minimum TLS version allowed for incoming client connections (1.0, 1.1, 1.2, 1.3). Default is 1.2."
  type        = string
  default     = "1.2"
}
