output "worker_profile_name" {
  description = "IAM instance profile name for worker nodes"
  value       = aws_iam_instance_profile.worker_profile.name
}


output "github_actions_role_arn" {
  description = "IAM Role ARN to configure in GitHub Variables"
  value       = try(aws_iam_role.github_actions_role[0].arn, null)
}

output "karpenter_node_role_name" {
  description = "IAM role name used by EC2 instances provisioned by Karpenter"
  value       = try(aws_iam_role.karpenter_node_role[0].name, null)
}

output "karpenter_node_instance_profile_name" {
  description = "IAM instance profile used by EC2 instances provisioned by Karpenter"
  value       = try(aws_iam_instance_profile.karpenter_node_profile[0].name, null)
}

output "karpenter_controller_policy_arn" {
  description = "IAM policy attached to the existing K3s worker role for Karpenter controller permissions"
  value       = try(aws_iam_policy.karpenter_controller_policy[0].arn, null)
}

output "karpenter_interruption_queue_name" {
  description = "SQS queue name used by Karpenter interruption handling"
  value       = try(aws_sqs_queue.karpenter_interruption_queue[0].name, null)
}
