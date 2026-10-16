output "applications" {
  description = "Map of created Access Applications with their IDs, AUDs, and domains"
  value = {
    for k, v in cloudflare_zero_trust_access_application.app : k => {
      id     = v.id
      aud    = v.aud
      domain = v.domain
      name   = v.name
    }
  }
}

output "policy_ids" {
  description = "Map of created Access Policy IDs keyed by application key"
  value       = { for k, v in cloudflare_zero_trust_access_policy.email_otp : k => v.id }
}
