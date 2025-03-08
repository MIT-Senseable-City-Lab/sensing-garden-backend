locals {
  api_schema = jsondecode(file("../common/api-schema.json"))
  # Using singular paths from the API schema
  detection_path = "/detection"
  classification_path = "/classification"
}

resource "aws_apigatewayv2_api" "http_api" {
  name          = "sensing-garden-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"]
    allow_methods = ["POST", "OPTIONS"]
    allow_origins = ["*"]  # In production, restrict this to specific domains
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id = aws_apigatewayv2_api.http_api.id
  name   = "data"
  auto_deploy = true
  default_route_settings {
    throttling_rate_limit = 100
    throttling_burst_limit = 100
  }
}

# Permission for API Gateway to invoke Detection Lambda
resource "aws_lambda_permission" "api_gateway_detection" {
  statement_id  = "AllowAPIGatewayInvokeDetection"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.detection_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*${local.detection_path}"
}

# Permission for API Gateway to invoke Classification Lambda
resource "aws_lambda_permission" "api_gateway_classification" {
  statement_id  = "AllowAPIGatewayInvokeClassification"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.classification_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*${local.classification_path}"
}

# Create integration for Detection Lambda
resource "aws_apigatewayv2_integration" "detection_lambda" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.detection_function.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

# Create integration for Classification Lambda
resource "aws_apigatewayv2_integration" "classification_lambda" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.classification_function.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

# Create route for Detection endpoint
resource "aws_apigatewayv2_route" "detection_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST ${local.detection_path}"
  target    = "integrations/${aws_apigatewayv2_integration.detection_lambda.id}"
  authorization_type = "NONE"
}

# Create route for Classification endpoint
resource "aws_apigatewayv2_route" "classification_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST ${local.classification_path}"
  target    = "integrations/${aws_apigatewayv2_integration.classification_lambda.id}"
  authorization_type = "NONE"
}

# API Keys are managed differently for HTTP APIs
# Using REST API Gateway resources for API key management
resource "aws_api_gateway_api_key" "api_key" {
  name = "my-api-key"
  enabled = true
}

# Create a usage plan for the API key
# Note: For HTTP APIs, we need to create a REST API Gateway usage plan
# and link it to our API key
resource "aws_api_gateway_usage_plan" "usage_plan" {
  name        = "standard-usage-plan"
  description = "Standard usage plan for API"
  
  # Note: HTTP APIs don't directly integrate with usage plans in the same way as REST APIs
  # This is a limitation of the current AWS API Gateway implementation
  # For production, consider using a REST API Gateway if API key management is critical
  
  quota_settings {
    limit  = 1000
    period = "DAY"
  }
  
  throttle_settings {
    burst_limit = 100
    rate_limit  = 50
  }
}

# Associate the API key with the usage plan
resource "aws_api_gateway_usage_plan_key" "usage_plan_key" {
  key_id        = aws_api_gateway_api_key.api_key.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.usage_plan.id
}
