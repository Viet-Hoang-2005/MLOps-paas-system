# Khung Secrets cho AWS Credentials
resource "aws_secretsmanager_secret" "aws_secrets" {
  name                    = "mlops/aws-secrets"
  description             = "AWS Credentials"
  recovery_window_in_days = 0
}

# Khung Secrets cho Production
resource "aws_secretsmanager_secret" "production_secrets" {
  name                    = "mlops/production-secrets"
  description             = "Secrets for K3s Cluster (ArgoCD, Postgres, Redis, etc)"
  recovery_window_in_days = 0
}

# Khung Secrets cho GitHub Actions
resource "aws_secretsmanager_secret" "github_actions_secrets" {
  name                    = "mlops/github-actions-secrets"
  description             = "Secrets for GitHub Actions CI/CD pipeline (Harbor)"
  recovery_window_in_days = 0
}

# K3s creates the agent token at runtime. Terraform owns only the secret
# container so the token value never enters Terraform state; Ansible publishes
# a secret version after the K3s server is initialized.
resource "aws_secretsmanager_secret" "karpenter_k3s_agent_token" {
  count                   = var.enable_karpenter ? 1 : 0
  name                    = "mlops/k3s-agent-token"
  description             = "K3s agent token for self-managed Karpenter nodes"
  recovery_window_in_days = 0
}

# A container without an AWSCURRENT version is not a readable secret: every
# client that compares the stored value before writing, Ansible included, hits
# ResourceNotFoundException. Terraform seeds a placeholder version so the
# container is always readable, and ignores the value afterwards so the real
# token published by Ansible is never reverted or copied into Terraform state.
resource "aws_secretsmanager_secret_version" "karpenter_k3s_agent_token_placeholder" {
  count     = var.enable_karpenter ? 1 : 0
  secret_id = aws_secretsmanager_secret.karpenter_k3s_agent_token[0].id
  secret_string = jsonencode({
    token = "pending-ansible-bootstrap"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
