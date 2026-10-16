# 1. Khởi tạo Access Applications cho từng ứng dụng cần bảo vệ
resource "cloudflare_zero_trust_access_application" "app" {
  for_each = {
    for k, v in var.applications : k => v
    if length(v.allowed_emails) > 0
  }

  zone_id          = var.zone_id
  name             = each.value.name
  domain           = each.value.domain
  type             = "self_hosted"
  session_duration = coalesce(each.value.session_duration, "24h")
}

# 2. Khởi tạo Access Policy xác thực Email OTP cho từng Access Application
resource "cloudflare_zero_trust_access_policy" "email_otp" {
  for_each = cloudflare_zero_trust_access_application.app

  zone_id        = var.zone_id
  application_id = each.value.id
  name           = "Allow Authorized Emails via OTP (${each.key})"
  precedence     = "1"
  decision       = "allow"

  include {
    email = var.applications[each.key].allowed_emails
  }
}
