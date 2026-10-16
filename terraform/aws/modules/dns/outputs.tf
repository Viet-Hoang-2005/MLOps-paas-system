output "certificate_arn" {
  description = "The ARN of the ACM certificate"
  value       = try(aws_acm_certificate_validation.mlops_cert_val[0].certificate_arn, null)
}

output "acm_domain_validation_options" {
  description = "CNAME records to add to Cloudflare DNS for SSL certificate validation"
  value       = try(aws_acm_certificate.mlops_cert[0].domain_validation_options, [])
}

output "karpenter_k3s_api_hostname" {
  description = "Stable private DNS hostname used by Karpenter-created K3s agents"
  value       = var.enable_karpenter_private_dns ? "k3s-api.${var.karpenter_private_zone_name}" : null
}

output "karpenter_k3s_api_endpoint" {
  description = "Stable private HTTPS endpoint used by Karpenter-created K3s agents"
  value       = var.enable_karpenter_private_dns ? "https://k3s-api.${var.karpenter_private_zone_name}:6443" : null
}
