variable "public_subnet_1a_id" {
  type = string
}

variable "private_subnet_1a_id" {
  type = string
}

variable "master_sg_id" {
  type = string
}

variable "worker_sg_id" {
  type = string
}

variable "worker_profile_name" {
  type = string
}

variable "key_name" {
  type    = string
  default = "mlops-keypair"
}

variable "master_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "worker_instance_type" {
  type    = string
  default = "t3.large"
}

variable "master_volume_size" {
  type    = number
  default = 40
}

variable "worker_instance_count" {
  type    = number
  default = 2
}

variable "worker_volume_size" {
  type    = number
  default = 40
}
