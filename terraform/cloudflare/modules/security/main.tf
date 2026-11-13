resource "cloudflare_zone_settings_override" "security_settings" {
  zone_id = var.zone_id

  settings {
    ssl              = var.ssl_mode
    always_use_https = "on"
    min_tls_version  = var.min_tls_version
    brotli           = "on"
    http3            = "on"
    tls_1_3          = "on"
  }
}

