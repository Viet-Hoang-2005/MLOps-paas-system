variable "budget_name" {
  description = "Name of the AWS Credit Budget"
  type        = string
  default     = "mlops-paas-credit-budget"
}

variable "credit_limit_amount" {
  description = "Total Credit limit or budget amount in USD to track"
  type        = number
  default     = 200
}

variable "currency" {
  description = "Currency unit for the budget"
  type        = string
  default     = "USD"
}

variable "budget_time_unit" {
  description = "Time unit for the budget: ANNUALLY (for full credit lifecycle) or MONTHLY"
  type        = string
  default     = "ANNUALLY"
}

variable "alert_recipient_emails" {
  description = "List of email addresses to receive budget and cost alerts"
  type        = list(string)
  default     = ["tnvhoang2005@gmail.com"]
}

variable "enable_anomaly_detection" {
  description = "Enable AWS Cost Anomaly Detection using machine learning"
  type        = bool
  default     = true
}

variable "anomaly_threshold_usd" {
  description = "Dollar threshold for anomaly impact before triggering an alert"
  type        = number
  default     = 10
}
