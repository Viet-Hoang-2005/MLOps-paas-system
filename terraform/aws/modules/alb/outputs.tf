output "lb_dns_name" {
  description = "DNS name of the Load Balancer"
  value       = aws_lb.api_alb.dns_name
}

output "target_group_arn" {
  description = "ARN of the K3s worker target group"
  value       = aws_lb_target_group.worker_tg.arn
}
