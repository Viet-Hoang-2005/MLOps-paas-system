output "acm_validation_record_names" {
  description = "List of created ACM validation record names"
  value       = [for r in cloudflare_record.acm_validation : r.hostname]
}

output "api_record_hostname" {
  description = "Hostname for the API DNS record"
  value       = length(cloudflare_record.api) > 0 ? cloudflare_record.api[0].hostname : null
}

output "registry_record_hostname" {
  description = "Hostname for the Harbor Registry DNS record"
  value       = length(cloudflare_record.registry) > 0 ? cloudflare_record.registry[0].hostname : null
}

output "tunnel_record_hostnames" {
  description = "Map of created Tunnel DNS hostnames"
  value       = { for k, r in cloudflare_record.tunnel_cnames : k => r.hostname }
}

