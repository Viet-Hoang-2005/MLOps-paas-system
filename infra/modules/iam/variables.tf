variable "artifacts_bucket_arn" {
  description = "ARN of the S3 bucket for artifacts"
  type        = string
}

variable "github_secrets_arn" {
  description = "ARN of the github secrets"
  type        = string
}

variable "github_actions_secrets_arn" {
  description = "ARN of the github actions secrets"
  type        = string
}

variable "mlflow_basic_auth_arn" {
  description = "ARN of the MLflow basic auth secrets"
  type        = string
}


variable "enable_github_oidc" {
  description = "Whether to create GitHub Actions OIDC and IAM resources"
  type        = bool
  default     = false
}

variable "enable_karpenter" {
  description = "Whether to create Karpenter IAM resources for the K3s cluster"
  type        = bool
  default     = false
}

variable "karpenter_cluster_name" {
  description = "Logical cluster name used by Karpenter discovery tags and IAM conditions"
  type        = string
  default     = "mlops-paas-cluster"
}

variable "karpenter_k3s_token_secret_arn" {
  description = "ARN of the only Secrets Manager secret Karpenter nodes may read during K3s bootstrap"
  type        = string
  default     = ""
}
