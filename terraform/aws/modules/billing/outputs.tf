output "budget_id" {
  description = "ID of the AWS Credit Budget"
  value       = aws_budgets_budget.credit_budget.id
}

output "budget_name" {
  description = "Name of the AWS Credit Budget"
  value       = aws_budgets_budget.credit_budget.name
}

output "anomaly_monitor_arn" {
  description = "ARN of the Cost Anomaly Monitor"
  value       = var.enable_anomaly_detection ? aws_ce_anomaly_monitor.service_monitor[0].arn : null
}

