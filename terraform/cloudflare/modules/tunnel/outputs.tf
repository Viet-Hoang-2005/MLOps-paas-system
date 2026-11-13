output "tunnel_id" {
  description = "The UUID of the Cloudflare Tunnel"
  value       = cloudflare_zero_trust_tunnel_cloudflared.tunnel.id
}

output "tunnel_name" {
  description = "The name of the Cloudflare Tunnel"
  value       = cloudflare_zero_trust_tunnel_cloudflared.tunnel.name
}

output "tunnel_cname" {
  description = "CNAME target for Cloudflare Tunnel"
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.tunnel.id}.cfargotunnel.com"
}

output "tunnel_token" {
  description = "The sensitive token required by cloudflared connector on K3s"
  value       = cloudflare_zero_trust_tunnel_cloudflared.tunnel.tunnel_token
  sensitive   = true
}

