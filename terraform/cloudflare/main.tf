# Module 1: Cloudflare Zero Trust Tunnel
# Quản lý đường hầm kết nối trực tiếp vào cụm K3s mà không cần mở port công khai
module "tunnel" {
  source = "./modules/tunnel"

  account_id      = var.cloudflare_account_id
  tunnel_name     = var.tunnel_name
  domain_name     = var.domain_name
  tunnel_services = var.tunnel_services
}

# Module 2: Cloudflare DNS Management
# Quản lý bản ghi xác thực ACM, CNAME AWS ALB và các CNAME dịch vụ nội bộ qua Tunnel
module "dns" {
  source = "./modules/dns"

  zone_id                = var.cloudflare_zone_id
  domain_name            = var.domain_name
  alb_dns_name           = var.alb_dns_name
  acm_validation_records = var.acm_validation_records
  api_proxied            = var.api_proxied
  tunnel_id              = module.tunnel.tunnel_id
  tunnel_services        = var.tunnel_services
}

# Module 3: Cloudflare Zone Security & Hardening
# Thiết lập SSL Full (Strict), bắt buộc HTTPS, tối ưu hóa HTTP/3 và TLS 1.2+
module "security" {
  source = "./modules/security"

  zone_id         = var.cloudflare_zone_id
  ssl_mode        = var.ssl_mode
  min_tls_version = var.min_tls_version
}
