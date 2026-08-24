variable "domain_name" {
  description = "Base domain name for AI PaaS system"
  type        = string
  default     = "mlops-nids-nt114.id.vn"
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Project name used for optional shared resources"
  type        = string
  default     = "mlops-paas"
}

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

variable "private_subnet_1a_cidr" {
  description = "CIDR block for Private Subnet 1a"
  type        = string
  default     = "10.0.2.0/24"
}

variable "public_subnet_1b_cidr" {
  description = "CIDR block for Public Subnet 1b"
  type        = string
  default     = "10.0.3.0/24"
}

variable "key_name" {
  description = "EC2 Key Pair name for Master and Worker nodes SSH access"
  type        = string
  default     = "mlops-keypair"
}

variable "master_instance_type" {
  description = "EC2 instance type for K3s Master node"
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for K3s Worker nodes"
  type        = string
  default     = "t3.large"
}

variable "master_volume_size" {
  description = "Root EBS volume size in GB for K3s Master node"
  type        = number
  default     = 40
}

variable "worker_instance_count" {
  description = "Number of EC2 Worker nodes for K3s cluster"
  type        = number
  default     = 2
}

variable "worker_volume_size" {
  description = "Root EBS volume size in GB for K3s Worker nodes"
  type        = number
  default     = 40
}

variable "enable_artifact_storage" {
  description = "Create the persistent S3 artifact bucket."
  type        = bool
  default     = true
}

variable "enable_secrets_manager" {
  description = "Create persistent Secrets Manager resources."
  type        = bool
  default     = true
}

variable "enable_github_oidc" {
  description = "Create GitHub Actions OIDC provider and deployment role."
  type        = bool
  default     = true
}

variable "enable_acm_certificate" {
  description = "Create the ACM certificate used by the public ALB."
  type        = bool
  default     = true
}

variable "enable_network" {
  description = "Create the VPC, subnets, route tables and Internet Gateway."
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "Create a NAT Gateway for private K3s workers."
  type        = bool
  default     = true
}

variable "enable_k3s_compute" {
  description = "Create the EC2 K3s server and static worker nodes."
  type        = bool
  default     = true
}

variable "enable_alb" {
  description = "Create the public ALB and target group for K3s ingress."
  type        = bool
  default     = true
}

variable "alb_idle_timeout_seconds" {
  description = "Maximum idle time for long-running API and Harbor registry uploads through the public ALB."
  type        = number
  default     = 600

  validation {
    condition     = var.alb_idle_timeout_seconds >= 60 && var.alb_idle_timeout_seconds <= 4000
    error_message = "alb_idle_timeout_seconds must be between 60 and 4000 seconds."
  }
}

variable "enable_karpenter" {
  description = "Create Karpenter IAM, queue and discovery resources."
  type        = bool
  default     = true
}

variable "karpenter_cluster_name" {
  description = "Logical cluster name used by Karpenter discovery tags and IAM conditions"
  type        = string
  default     = "mlops-paas-cluster"
}
