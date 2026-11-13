# 1. ACM Certificate Validation DNS Records
resource "cloudflare_record" "acm_validation" {
  for_each = { for record in var.acm_validation_records : record.name => record }

  zone_id = var.zone_id
  name    = each.value.name
  content = each.value.record
  type    = each.value.type
  proxied = false
  ttl     = 60
  comment = "AWS ACM SSL Certificate Validation"
}

# 2. Control Plane API Subdomain -> AWS ALB
resource "cloudflare_record" "api" {
  count = var.alb_dns_name != "" ? 1 : 0

  zone_id = var.zone_id
  name    = "api"
  content = var.alb_dns_name
  type    = "CNAME"
  proxied = var.api_proxied
  ttl     = var.api_proxied ? 1 : 300
  comment = "MLOps PaaS Control Plane API -> AWS ALB"
}

# 3. Harbor Container Registry Subdomain -> AWS ALB
# proxied = false (DNS-only) để tránh giới hạn payload 100 MB của Cloudflare Free
resource "cloudflare_record" "registry" {
  count = var.alb_dns_name != "" ? 1 : 0

  zone_id = var.zone_id
  name    = "registry"
  content = var.alb_dns_name
  type    = "CNAME"
  proxied = false
  ttl     = 300
  comment = "Harbor OCI Registry -> AWS ALB (Direct connection, bypasses 100MB limit)"
}

# 4. Cloudflare Zero Trust Tunnel Hostnames (Dynamic from tunnel_services)
# Bao gồm Apex (@), argocd, workflow, grafana và bất kỳ dịch vụ mở rộng nào
resource "cloudflare_record" "tunnel_cnames" {
  for_each = var.tunnel_services

  zone_id = var.zone_id
  name    = each.key
  content = "${var.tunnel_id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
  comment = each.value.description != "" ? each.value.description : "Cloudflare Tunnel -> K3s service: ${each.key}"
}
