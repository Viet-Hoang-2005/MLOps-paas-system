output "master_public_ip" {
  description = "Public IP for SSH access to Master Node"
  value       = local.enable_k3s_compute_stack ? module.compute[0].master_public_ip : null
}

output "master_private_ip" {
  description = "Private IP of Master Node inside VPC"
  value       = local.enable_k3s_compute_stack ? module.compute[0].master_private_ip : null
}

output "worker_private_ips" {
  description = "List of Private IPs of Worker Nodes inside VPC"
  value       = local.enable_k3s_compute_stack ? module.compute[0].worker_private_ips : []
}

output "vpc_id" {
  description = "VPC containing the K3s cluster"
  value       = var.enable_network ? module.network[0].vpc_id : null
}

output "ec2_key_pair_name" {
  description = "EC2 key pair expected by the Ansible control host"
  value       = local.enable_k3s_compute_stack ? var.key_name : null
}

output "alb_dns" {
  description = "Application Load Balancer AWS Domain"
  value       = local.enable_alb_stack ? module.alb[0].lb_dns_name : null
}

output "alb_target_group_arn" {
  description = "Target group used to validate K3s worker health"
  value       = local.enable_alb_stack ? module.alb[0].target_group_arn : null
}

output "frontend_url" {
  description = "Public URL for ReactJS Dashboard"
  value       = local.enable_alb_stack ? "https://${var.domain_name}" : null
}

output "api_url" {
  description = "Public URL for Django Control Plane API"
  value       = local.enable_alb_stack ? "https://api.${var.domain_name}" : null
}

output "s3_bucket_name" {
  description = "Model Storage Bucket"
  value       = var.enable_artifact_storage ? module.storage[0].bucket_id : null
}

output "github_actions_role_arn" {
  description = "IAM Role ARN to configure in GitHub Variables"
  value       = var.enable_github_oidc && local.enable_shared_iam ? module.iam[0].github_actions_role_arn : null
}

output "karpenter_node_role_name" {
  description = "IAM role name used by EC2 instances provisioned by Karpenter"
  value       = local.enable_karpenter_stack ? module.iam[0].karpenter_node_role_name : null
}

output "karpenter_node_instance_profile_name" {
  description = "IAM instance profile name to set in EC2NodeClass.spec.instanceProfile"
  value       = local.enable_karpenter_stack ? module.iam[0].karpenter_node_instance_profile_name : null
}

output "karpenter_controller_policy_arn" {
  description = "IAM policy attached to the K3s worker role for Karpenter controller permissions"
  value       = local.enable_karpenter_stack ? module.iam[0].karpenter_controller_policy_arn : null
}

output "karpenter_interruption_queue_name" {
  description = "SQS queue name to pass as KARPENTER_INTERRUPTION_QUEUE"
  value       = local.enable_karpenter_stack ? module.iam[0].karpenter_interruption_queue_name : null
}

output "karpenter_k3s_api_hostname" {
  description = "Stable private DNS hostname used by Karpenter-created K3s agents"
  value       = local.enable_karpenter_stack ? module.dns[0].karpenter_k3s_api_hostname : null
}

output "karpenter_k3s_api_endpoint" {
  description = "Stable private API endpoint used by Karpenter-created K3s agents"
  value       = local.enable_karpenter_stack ? module.dns[0].karpenter_k3s_api_endpoint : null
}

output "karpenter_k3s_token_secret_arn" {
  description = "ARN of the K3s agent-token secret container; the token value is published by Ansible"
  value       = local.enable_karpenter_stack ? module.secrets[0].karpenter_k3s_token_secret_arn : null
}

output "acm_ssl_validation_records" {
  description = "CNAME records to copy to Cloudflare DNS table to validate ACM SSL Certificate"
  value       = var.enable_acm_certificate ? module.dns[0].acm_domain_validation_options : null
}
