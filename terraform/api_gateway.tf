resource "aws_apigatewayv2_api" "http_api" {
  name          = "my-api-gateway"
  protocol_type = "HTTP"
  api_key_source = "HEADER"
  
  cors_configuration {
    allow_headers = ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"]
    allow_methods = ["POST", "OPTIONS"]
    allow_origins = ["*"]  # In production, restrict this to specific domains
    max_age       = 300
  }
}

resource "aws_apigatewayv2_api_key" "api_key" {
  name = "my-api-key"
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

resource "aws_apigatewayv2_integration" "lambda" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.write_data.invoke_arn
}

resource "aws_apigatewayv2_route" "post_data" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /data"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = "NONE"
}

# Create a usage plan for the API key
resource "aws_api_gateway_usage_plan" "usage_plan" {
  name        = "standard-usage-plan"
  description = "Standard usage plan for API"
  
  api_stages {
    api_id = aws_apigatewayv2_api.http_api.id
    stage  = aws_apigatewayv2_stage.default.name
  }
  
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
  key_id        = aws_apigatewayv2_api_key.api_key.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.usage_plan.id
}
