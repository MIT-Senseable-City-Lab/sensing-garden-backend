# Fleet monitoring (SPEC-fleet-monitoring-and-notifications, rollout step 1).
# Monitoring is trigger-resident: no new Lambda — the trigger function gains an
# EventBridge schedule (liveness sweep; a dead device emits no S3 event, so
# absence is only detectable by a clock) and a per-device state table.

variable "monitor_ntfy_emergency_url" {
  description = "ntfy topic URL for emergency notifications: liveness, disk space, log errors, bandwidth cap (empty = channel disabled)"
  type        = string
  default     = ""
}

variable "monitor_ntfy_general_url" {
  description = "ntfy topic URL for general notifications: warnings, digests, backdrop images (empty = channel disabled)"
  type        = string
  default     = ""
}

variable "monitor_slack_emergency_url" {
  description = "Slack incoming webhook URL for emergency notifications (empty = channel disabled)"
  type        = string
  default     = ""
}

variable "monitor_slack_general_url" {
  description = "Slack incoming webhook URL for general notifications (empty = channel disabled)"
  type        = string
  default     = ""
}

variable "monitor_healthchecks_ping_url" {
  description = "Healthchecks.io ping URL, hit as the last action of each sweep (empty = disabled)"
  type        = string
  default     = ""
}

data "aws_region" "current" {}

resource "aws_dynamodb_table" "monitor_state" {
  name         = "sensing-garden-monitor-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"

  attribute {
    name = "device_id"
    type = "S"
  }
}

resource "aws_iam_role_policy" "trigger_lambda_monitoring_policy" {
  name = "trigger-lambda-monitoring-policy"
  role = aws_iam_role.trigger_lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.monitor_state.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan"]
        Resource = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/sensing-garden-devices"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/sensing-garden-heartbeats"
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:Query"]
        Resource = [
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/sensing-garden-tracks",
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/sensing-garden-tracks/index/device_id_index"
        ]
      }
    ]
  })
}

resource "aws_cloudwatch_event_rule" "monitoring_sweep" {
  name                = "sensing-garden-monitoring-sweep"
  description         = "Liveness sweep + Healthchecks dead-man ping via the trigger Lambda"
  schedule_expression = "rate(10 minutes)"
}

resource "aws_cloudwatch_event_target" "monitoring_sweep" {
  rule = aws_cloudwatch_event_rule.monitoring_sweep.name
  arn  = aws_lambda_function.trigger_handler_function.arn
}

resource "aws_lambda_permission" "eventbridge_invoke_trigger" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger_handler_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.monitoring_sweep.arn
}

resource "aws_cloudwatch_event_rule" "monitoring_digest" {
  name                = "sensing-garden-monitoring-digest"
  description         = "Per-device new-track digest via the trigger Lambda (general route)"
  schedule_expression = "rate(8 hours)"
}

resource "aws_cloudwatch_event_target" "monitoring_digest" {
  rule = aws_cloudwatch_event_rule.monitoring_digest.name
  arn  = aws_lambda_function.trigger_handler_function.arn
  # Custom input replaces the default schedule event body, so "source" is set
  # explicitly here to keep matching the same dispatch check as the sweep rule.
  input = jsonencode({ source = "aws.events", task = "digest" })
}

resource "aws_lambda_permission" "eventbridge_invoke_trigger_digest" {
  statement_id  = "AllowEventBridgeInvokeDigest"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger_handler_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.monitoring_digest.arn
}
