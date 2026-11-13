variable "enable_karpenter" {
  description = "Whether to create the K3s agent-token secret container for Karpenter nodes"
  type        = bool
  default     = false
}
