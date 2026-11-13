# 1. Sinh ngẫu nhiên chuỗi bảo mật 32-byte (Base64) cho Cloudflare Tunnel
resource "random_id" "tunnel_secret" {
  byte_length = 32
}

# 2. Khởi tạo Cloudflare Zero Trust Tunnel với cấu hình quản lý từ Cloudflare
resource "cloudflare_zero_trust_tunnel_cloudflared" "tunnel" {
  account_id = var.account_id
  name       = var.tunnel_name
  secret     = random_id.tunnel_secret.b64_std
  config_src = "cloudflare"
}

# 3. Cấu hình Ingress Rules cho Tunnel
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "tunnel_config" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.tunnel.id

  config {
    # Định tuyến động các dịch vụ nội bộ K3s (Web, Argo CD, Argo Workflows, Grafana, ...)
    dynamic "ingress_rule" {
      for_each = var.tunnel_services
      content {
        hostname = ingress_rule.key == "@" ? var.domain_name : "${ingress_rule.key}.${var.domain_name}"
        service  = ingress_rule.value.service

        dynamic "origin_request" {
          for_each = ingress_rule.value.no_tls_verify ? [1] : []
          content {
            no_tls_verify = true
          }
        }
      }
    }

    # Quy tắc mặc định (Catch-all) ở cuối cùng của danh sách ingress
    ingress_rule {
      service = "http_status:404"
    }
  }
}
