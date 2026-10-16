# Cloudflare Zero Trust Tunnel Outputs
output "tunnel_id" {
  description = "The UUID of the Cloudflare Zero Trust Tunnel"
  value       = module.tunnel.tunnel_id
}

output "tunnel_name" {
  description = "The human-readable name of the Cloudflare Tunnel"
  value       = module.tunnel.tunnel_name
}

output "tunnel_cname" {
  description = "CNAME target domain for the Cloudflare Tunnel"
  value       = module.tunnel.tunnel_cname
}

output "tunnel_token" {
  description = "Sensitive token used by cloudflared connector on K3s (sync to AWS Secrets Manager)"
  value       = module.tunnel.tunnel_token
  sensitive   = true
}

# Service Endpoints
output "frontend_url" {
  description = "MLOps PaaS Web Dashboard"
  value       = "https://${var.domain_name}"
}

output "api_endpoint" {
  description = "MLOps PaaS Control Plane API Endpoint"
  value       = "https://api.${var.domain_name}/api/"
}

output "headlamp_url" {
  description = "Kubernetes Web UI Headlamp URL"
  value       = "https://headlamp.${var.domain_name}"
}

output "argocd_url" {
  description = "Argo CD GitOps Dashboard URL"
  value       = "https://argocd.${var.domain_name}"
}

output "workflow_url" {
  description = "Argo Workflows UI URL"
  value       = "https://workflow.${var.domain_name}"
}

output "grafana_url" {
  description = "Grafana Monitoring Dashboard URL"
  value       = "https://grafana.${var.domain_name}"
}

output "harbor_registry_url" {
  description = "Harbor Container Registry URL"
  value       = "https://registry.${var.domain_name}"
}

# Informational Outputs
output "acm_validation_record_names" {
  description = "List of created ACM validation CNAME record names"
  value       = module.dns.acm_validation_record_names
}

output "configured_tunnel_services" {
  description = "Map of all subdomains and internal services exposed via the tunnel"
  value       = { for k, v in var.tunnel_services : k => v.service }
}

# Cloudflare Zero Trust Access Outputs
output "access_protected_applications" {
  description = "Map of all applications actively protected by Cloudflare Access Email OTP"
  value       = module.access.applications
}

output "argo_workflow_access_application_id" {
  description = "ID of the Cloudflare Access Application protecting Argo Workflows"
  value       = lookup(module.access.applications, "argo-workflows", null) != null ? module.access.applications["argo-workflows"].id : null
}

output "headlamp_access_application_id" {
  description = "ID of the Cloudflare Access Application protecting Headlamp"
  value       = lookup(module.access.applications, "headlamp", null) != null ? module.access.applications["headlamp"].id : null
}