output "aws_secrets_arn" {
  value = aws_secretsmanager_secret.aws_secrets.arn
}

output "github_actions_secrets_arn" {
  value = aws_secretsmanager_secret.github_actions_secrets.arn
}

output "production_secrets_arn" {
  value = aws_secretsmanager_secret.production_secrets.arn
}

output "karpenter_k3s_token_secret_arn" {
  description = "ARN of the Terraform-owned K3s agent-token secret container"
  value       = try(aws_secretsmanager_secret.karpenter_k3s_agent_token[0].arn, null)
}
