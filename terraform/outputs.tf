# Consolidated outputs for all resources

# API Gateway outputs
output "api_gateway_url" {
  value       = aws_apigatewayv2_api.http_api.api_endpoint
  description = "Base URL for API Gateway"
}

output "detection_api_endpoint" {
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/detections"
  description = "Full URL for the detections endpoint"
}

output "classification_api_endpoint" {
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/classifications"
  description = "Full URL for the classifications endpoint"
}

output "models_api_endpoint" {
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/models"
  description = "Full URL for the models endpoint"
}

output "test_api_key" {
  value       = aws_api_gateway_api_key.test_key.value
  description = "Test environment API key for authentication"
  sensitive   = true
}

output "edge_api_key" {
  value       = aws_api_gateway_api_key.edge_key.value
  description = "Edge/production environment API key for authentication"
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
output "api_handler_lambda_function_name" {
  value       = aws_lambda_function.api_handler_function.function_name
  description = "Name of the API handler Lambda function"
}

# Direct Lambda invocation examples
output "detection_api_invoke_command" {
  value       = "aws lambda invoke --function-name ${aws_lambda_function.api_handler_function.function_name} --payload '{\"path\":\"/detections\",\"httpMethod\":\"POST\",\"body\":\"{\\\"device_id\\\":\\\"device123\\\",\\\"model_id\\\":\\\"model456\\\",\\\"image\\\":\\\"base64_data\\\"}\"}' response.json"
  description = "Example command to invoke detection API directly"
}

output "classification_api_invoke_command" {
  value       = "aws lambda invoke --function-name ${aws_lambda_function.api_handler_function.function_name} --payload '{\"path\":\"/classifications\",\"httpMethod\":\"POST\",\"body\":\"{\\\"device_id\\\":\\\"device123\\\",\\\"model_id\\\":\\\"model456\\\",\\\"image\\\":\\\"base64_data\\\",\\\"genus\\\":\\\"Test Genus\\\",\\\"family\\\":\\\"Test Family\\\",\\\"species\\\":\\\"Test Species\\\",\\\"confidence\\\":0.95}\"}' response.json"
  description = "Example command to invoke classification API directly"
}