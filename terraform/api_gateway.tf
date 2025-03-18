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

# API Keys are managed differently for HTTP APIs
# Using REST API Gateway resources for API key management
resource "aws_api_gateway_api_key" "api_key" {
  name = "sensing-garden-api-key"
  enabled = true
}

resource "aws_apigatewayv2_stage" "default" {
  api_id = aws_apigatewayv2_api.http_api.id
  name   = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_rate_limit = 100
    throttling_burst_limit = 100
  }
}

# Integration for detections
resource "aws_apigatewayv2_integration" "detection_lambda" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.detection_function.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

# Integration for classifications
resource "aws_apigatewayv2_integration" "classification_lambda" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.classification_function.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

# Route for detections
resource "aws_apigatewayv2_route" "post_detections" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /detection"
  target    = "integrations/${aws_apigatewayv2_integration.detection_lambda.id}"
  authorization_type = "NONE"
}

# Route for classifications
resource "aws_apigatewayv2_route" "post_classifications" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /classification"
  target    = "integrations/${aws_apigatewayv2_integration.classification_lambda.id}"
  authorization_type = "NONE"
}

# Create a usage plan for the API key
# Note: For HTTP APIs, we need to create a REST API Gateway usage plan
# and link it to our API key
resource "aws_api_gateway_usage_plan" "usage_plan" {
  name        = "sensing-garden-usage-plan"
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
