variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "lb_sg_id" {
  type = string
}

variable "worker_instance_ids" {
  type = list(string)
}

variable "certificate_arn" {
  type = string
}

variable "idle_timeout_seconds" {
  description = "Maximum idle time for client connections through the ALB."
  type        = number
}
