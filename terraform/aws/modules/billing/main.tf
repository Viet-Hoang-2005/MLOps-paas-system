# AWS Budgets: Theo dõi tổng Credit tiêu thụ và gửi cảnh báo đến email
resource "aws_budgets_budget" "credit_budget" {
  name         = var.budget_name
  budget_type  = "COST"
  limit_amount = tostring(var.credit_limit_amount)
  limit_unit   = var.currency
  time_unit    = var.budget_time_unit

  cost_types {
    include_credit             = true
    include_discount           = true
    include_other_subscription = true
    include_recurring          = true
    include_refund             = false
    include_subscription       = true
    include_support            = true
    include_tax                = true
    include_upfront            = true
    use_amortized              = false
    use_blended                = false
  }

  # Ngưỡng 1: Đã tiêu 50% Credit (Thông tin tiến độ)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_recipient_emails
  }

  # Ngưỡng 2: Đã tiêu 80% Credit (Cảnh báo tối ưu tài nguyên)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_recipient_emails
  }

  # Ngưỡng 3: Đã tiêu 100% Credit (Khẩn cấp: Chạm trần Credit, sắp trừ tiền thẻ)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_recipient_emails
  }

  # Ngưỡng 4: Dự báo (Forecasted) sẽ vượt 100% Credit trong chu kỳ
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_recipient_emails
  }
}

# AWS Cost Anomaly Detection: Giám sát đột biến chi phí bất thường bằng ML
resource "aws_ce_anomaly_monitor" "service_monitor" {
  count             = var.enable_anomaly_detection ? 1 : 0
  name              = "mlops-paas-cost-anomaly-monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "email_subscription" {
  count            = var.enable_anomaly_detection ? 1 : 0
  name             = "mlops-paas-anomaly-alert"
  frequency        = "IMMEDIATE"
  monitor_arn_list = [aws_ce_anomaly_monitor.service_monitor[0].arn]

  subscriber {
    type    = "EMAIL"
    address = var.alert_recipient_emails[0]
  }

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      values        = [tostring(var.anomaly_threshold_usd)]
      match_options = ["GREATER_THAN_OR_EQUAL"]
    }
  }
}

