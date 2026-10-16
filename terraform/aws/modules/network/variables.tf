variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_1a_cidr" {
  description = "CIDR block for Public Subnet 1a"
  type        = string
  default     = "10.0.1.0/24"
}

variable "public_subnet_1b_cidr" {
  description = "CIDR block for Public Subnet 1b"
  type        = string
  default     = "10.0.3.0/24"
}

variable "private_subnet_1a_cidr" {
  description = "CIDR block for Private Subnet 1a"
  type        = string
  default     = "10.0.2.0/24"
}

variable "enable_nat_gateway" {
  description = "Whether to create NAT Gateway and private subnet default route"
  type        = bool
  default     = false
}

variable "enable_karpenter" {
  description = "Whether to tag subnets for Karpenter discovery"
  type        = bool
  default     = false
}

variable "karpenter_cluster_name" {
  description = "Karpenter discovery tag value"
  type        = string
  default     = "mlops-paas-cluster"
}
