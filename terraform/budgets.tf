# Spend guardrails (SPEC-fleet-monitoring item 14). Zero-code, sequence-
# independent — the highest-value alert in the stack given the request-cost
# runaway history. Both resources no-op until budget_alert_email is set.

variable "budget_alert_email" {
  description = "Recipient for budget threshold and cost-anomaly alerts (empty = disabled)"
  type        = string
  default     = ""
}

variable "monthly_budget_limit_eur_equivalent_usd" {
  description = "Monthly cost budget in USD (AWS Budgets bills in USD)"
  type        = string
  default     = "500"
}

resource "aws_budgets_budget" "monthly_cost" {
  count        = var.budget_alert_email == "" ? 0 : 1
  name         = "sensing-garden-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_limit_eur_equivalent_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}

resource "aws_ce_anomaly_monitor" "services" {
  count             = var.budget_alert_email == "" ? 0 : 1
  name              = "sensing-garden-service-anomalies"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "email" {
  count            = var.budget_alert_email == "" ? 0 : 1
  name             = "sensing-garden-anomaly-alerts"
  frequency        = "DAILY"
  monitor_arn_list = [aws_ce_anomaly_monitor.services[0].arn]

  subscriber {
    type    = "EMAIL"
    address = var.budget_alert_email
  }

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = ["50"]
    }
  }
}
