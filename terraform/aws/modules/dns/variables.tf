variable "domain_name" {
  description = "The base domain name for the AI PaaS"
  type        = string
  default     = "mlops-nids-nt114.id.vn"
}

variable "enable_acm_certificate" {
  description = "Whether to create the public ACM certificate"
  type        = bool
  default     = true
}

variable "enable_karpenter_private_dns" {
  description = "Whether to create the private K3s API DNS zone and record"
  type        = bool
  default     = false
}

variable "vpc_id" {
  description = "VPC associated with the private K3s API hosted zone"
  type        = string
  default     = ""
}

variable "master_private_ip" {
  description = "Private IPv4 address of the K3s server"
  type        = string
  default     = ""
}

variable "karpenter_private_zone_name" {
  description = "Private Route53 zone used by elastic K3s agents"
  type        = string
  default     = "internal.mlops-nids-nt114.id.vn"
}
