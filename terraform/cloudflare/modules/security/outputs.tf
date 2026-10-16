output "ssl_setting" {
  description = "Configured SSL setting mode"
  value       = cloudflare_zone_settings_override.security_settings.settings[0].ssl
}

output "min_tls_version" {
  description = "Configured minimum TLS version"
  value       = cloudflare_zone_settings_override.security_settings.settings[0].min_tls_version
}

