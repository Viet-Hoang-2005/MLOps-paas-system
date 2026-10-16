output "master_public_ip" {
  description = "Public IP for SSH access to Master Node"
  value       = aws_eip.master_eip.public_ip
}

output "worker_instance_ids" {
  description = "List of Worker Instance IDs"
  value       = aws_instance.worker_nodes[*].id
}

output "master_private_ip" {
  description = "Private IP of Master Node inside VPC"
  value       = aws_instance.master_node.private_ip
}

output "worker_private_ips" {
  description = "List of Private IPs of Worker Nodes inside VPC"
  value       = aws_instance.worker_nodes[*].private_ip
}
