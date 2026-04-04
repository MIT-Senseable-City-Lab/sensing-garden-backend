# Lambda deployment packages are built by scripts/build_lambda.sh
# Run it before terraform apply to bundle dependencies (pydantic, boto3, etc.)
# The script creates deployment_package.zip in each lambda/trigger directory.

# Attach permissions for Lambda to access DynamoDB
resource "aws_iam_role_policy_attachment" "lambda_dynamodb_access" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

# Attach permissions for Lambda to access S3
resource "aws_iam_role_policy_attachment" "lambda_s3_access" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# Single Lambda function for all API operations
resource "aws_lambda_function" "api_handler_function" {
  function_name    = "sensing-garden-api-handler"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.handler"
  runtime          = "python3.11"
  filename         = "${path.module}/../lambda/deployment_package.zip"
  source_code_hash = filebase64sha256("${path.module}/../lambda/deployment_package.zip")
  timeout          = 30  # Longer timeout for pagination and processing
  memory_size      = 256 # Increased memory for better performance

  environment {
    variables = {
      IMAGES_BUCKET       = "scl-sensing-garden-images"
      VIDEOS_BUCKET       = "scl-sensing-garden-videos"
      OUTPUT_BUCKET       = "scl-sensing-garden"
      TRACKS_TABLE        = "sensing-garden-tracks"
      HEARTBEATS_TABLE    = "sensing-garden-heartbeats"
      DEVICE_API_KEYS_TABLE = "sensing-garden-device-api-keys"
      SETUP_CODE            = var.setup_code
      TEST_API_KEY        = aws_api_gateway_api_key.test_key.value
      EDGE_API_KEY        = aws_api_gateway_api_key.edge_key.value
      FRONTEND_API_KEY    = aws_api_gateway_api_key.frontend_key.value
      DEPLOYMENTS_API_KEY = aws_api_gateway_api_key.deployments_key.value
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

# =============================================================================
# Trigger Lambda - processes S3 output uploads
# =============================================================================

# IAM role for trigger Lambda
resource "aws_iam_role" "trigger_lambda_exec" {
  name = "trigger_lambda_exec_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# CloudWatch Logs policy for trigger Lambda
resource "aws_iam_role_policy_attachment" "trigger_lambda_logs" {
  role       = aws_iam_role.trigger_lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB policy for trigger Lambda
resource "aws_iam_role_policy" "trigger_lambda_dynamodb_policy" {
  name = "trigger-lambda-dynamodb-policy"
  role = aws_iam_role.trigger_lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:BatchGetItem",
          "dynamodb:DescribeTable",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.tracks.arn,
          "${aws_dynamodb_table.tracks.arn}/index/*",
          aws_dynamodb_table.sensor_classifications.arn,
          "${aws_dynamodb_table.sensor_classifications.arn}/index/*",
          aws_dynamodb_table.devices.arn,
          aws_dynamodb_table.videos.arn,
          aws_dynamodb_table.heartbeats.arn,
        ]
      }
    ]
  })
}

# S3 read policy for trigger Lambda
resource "aws_iam_role_policy" "trigger_lambda_s3_policy" {
  name = "trigger-lambda-s3-policy"
  role = aws_iam_role.trigger_lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.output.arn,
          "${aws_s3_bucket.output.arn}/*"
        ]
      }
    ]
  })
}

# Trigger Lambda function
resource "aws_lambda_function" "trigger_handler_function" {
  function_name    = "sensing-garden-trigger-handler"
  role             = aws_iam_role.trigger_lambda_exec.arn
  handler          = "trigger_handler.lambda_handler"
  runtime          = "python3.11"
  filename         = "${path.module}/../trigger/deployment_package.zip"
  source_code_hash = filebase64sha256("${path.module}/../trigger/deployment_package.zip")
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      TRACKS_TABLE          = "sensing-garden-tracks"
      CLASSIFICATIONS_TABLE = "sensing-garden-classifications"
      DEVICES_TABLE         = "sensing-garden-devices"
      VIDEOS_TABLE          = "sensing-garden-videos"
      HEARTBEATS_TABLE      = "sensing-garden-heartbeats"
      OUTPUT_BUCKET         = "scl-sensing-garden"
    }
  }
}

# Permission for S3 to invoke trigger Lambda
resource "aws_lambda_permission" "s3_invoke_trigger" {
  statement_id  = "AllowS3InvokeTrigger"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger_handler_function.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.output.arn
}

# S3 event notification to trigger Lambda on output uploads
resource "aws_s3_bucket_notification" "output_bucket_notification" {
  bucket = aws_s3_bucket.output.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.trigger_handler_function.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "v1/"
  }

  depends_on = [aws_lambda_permission.s3_invoke_trigger]
}
