# Consolidated outputs for all resources

# API Gateway outputs
output "api_gateway_url" {
  value       = aws_apigatewayv2_api.http_api.api_endpoint
  description = "Base URL for API Gateway"
}

output "api_endpoint" {
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/data"
  description = "Full URL for the data endpoint"
}

output "api_key" {
  value       = aws_api_gateway_api_key.api_key.value
  description = "API key for authentication"
  sensitive   = true
}

# S3 outputs
output "s3_bucket_name" {
  value       = aws_s3_bucket.sensor_images.id
  description = "Name of the S3 bucket for sensor images"
}

# DynamoDB outputs
output "dynamodb_table_name" {
  value       = aws_dynamodb_table.sensor_detections.name
  description = "Name of the DynamoDB table for sensor detections"
}

output "classifications_table_name" {
  value       = aws_dynamodb_table.sensor_classifications.name
  description = "Name of the DynamoDB table for classifications"
}

output "models_table_name" {
  value       = aws_dynamodb_table.models.name
  description = "Name of the DynamoDB table for models"
}

# Lambda outputs
output "lambda_function_name" {
  value       = aws_lambda_function.write_data.function_name
  description = "Name of the Lambda function"
}

# Direct Lambda invocation example
output "lambda_invoke_command" {
  value       = "aws lambda invoke --function-name ${aws_lambda_function.write_data.function_name} --payload '{\"device_id\":\"device123\",\"model_id\":\"model456\",\"image\":\"base64_data\"}' response.json"
  description = "Example command to invoke Lambda directly"
}