output "lb_sg_id" {
  description = "ID of the load balancer security group"
  value       = try(aws_security_group.lb_sg[0].id, null)
}

output "master_sg_id" {
  description = "ID of the master node security group"
  value       = try(aws_security_group.master_sg[0].id, null)
}

output "worker_sg_id" {
  description = "ID of the worker node security group"
  value       = try(aws_security_group.worker_sg[0].id, null)
}
