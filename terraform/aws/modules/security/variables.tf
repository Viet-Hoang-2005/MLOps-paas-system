variable "vpc_id" {
  description = "VPC ID where security groups will be created"
  type        = string
}

variable "enable_legacy_security_groups" {
  description = "Whether to create security groups for legacy K3s and ALB resources"
  type        = bool
  default     = false
}

variable "enable_karpenter" {
  description = "Whether to tag worker security group for Karpenter discovery"
  type        = bool
  default     = false
}

variable "karpenter_cluster_name" {
  description = "Karpenter discovery tag value"
  type        = string
  default     = "mlops-paas-cluster"
}
