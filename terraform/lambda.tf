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
    content  = file("${path.module}/../common/schema.json")
    filename = "schema.json"
  }
}

# Create Lambda layer with the schema
resource "aws_lambda_layer_version" "schema_layer" {
  layer_name = "schema-layer"
  filename   = data.archive_file.schema_layer_zip.output_path
  source_code_hash = data.archive_file.schema_layer_zip.output_base64sha256
  compatible_runtimes = ["python3.9"]
}

# Lambda function for detections
resource "aws_lambda_function" "detection_function" {
  function_name    = "detection-function"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "handler.detection"
  runtime         = "python3.9"
  filename        = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout         = 10
  layers          = [aws_lambda_layer_version.schema_layer.arn]
}

# Lambda function for classifications
resource "aws_lambda_function" "classification_function" {
  function_name    = "classification-function"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "handler.classification"
  runtime         = "python3.9"
  filename        = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout         = 10
  layers          = [aws_lambda_layer_version.schema_layer.arn]
}

resource "aws_iam_role" "lambda_exec" {
  name = "lambda_exec_role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
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

# Permission for API Gateway to invoke Detection Lambda
resource "aws_lambda_permission" "api_gateway_detection" {
  statement_id  = "AllowAPIGatewayInvokeDetection"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.detection_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*/detections"
}

# Permission for API Gateway to invoke Classification Lambda
resource "aws_lambda_permission" "api_gateway_classification" {
  statement_id  = "AllowAPIGatewayInvokeClassification"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.classification_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*/classifications"
}