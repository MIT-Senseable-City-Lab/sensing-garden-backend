# Archive the Lambda source code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/src"
  output_path = "${path.module}/../lambda/deployment_package.zip"
}

# Create an archive for the schema layer
data "archive_file" "schema_layer_zip" {
  type        = "zip"
  output_path = "${path.module}/../lambda/schema_layer.zip"
  
  source {
    content  = file("${path.module}/../common/api-schema.json")
    filename = "api-schema.json"
  }
  
  source {
    content  = file("${path.module}/../common/db-schema.json")
    filename = "db-schema.json"
  }
}

# Create Lambda layer with the schema
resource "aws_lambda_layer_version" "schema_layer" {
  layer_name = "schema-layer"
  filename   = data.archive_file.schema_layer_zip.output_path
  source_code_hash = data.archive_file.schema_layer_zip.output_base64sha256
  compatible_runtimes = ["python3.9"]
}

# Attach permissions for Lambda to access DynamoDB
resource "aws_iam_policy_attachment" "lambda_dynamodb_access" {
  name       = "lambda-dynamodb-access"
  roles      = [aws_iam_role.lambda_exec.name]
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

# Attach permissions for Lambda to access S3
resource "aws_iam_policy_attachment" "lambda_s3_access" {
  name       = "lambda-s3-access"
  roles      = [aws_iam_role.lambda_exec.name]
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# Single Lambda function for all API operations
resource "aws_lambda_function" "api_handler_function" {
  function_name    = "sensing-garden-api-handler"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "handler.handler"
  runtime         = "python3.9"
  filename        = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout         = 30  # Longer timeout for pagination and processing
  memory_size     = 256 # Increased memory for better performance
  layers          = [aws_lambda_layer_version.schema_layer.arn]
  
  environment {
    variables = {
      IMAGES_BUCKET = "scl-sensing-garden-images"
      VIDEOS_BUCKET = "scl-sensing-garden-videos"
    }
  }
}

# Permission for API Gateway to invoke API Handler Lambda for all routes
resource "aws_lambda_permission" "api_gateway_api_handler" {
  statement_id  = "AllowAPIGatewayInvokeAPIHandler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*/*"
}