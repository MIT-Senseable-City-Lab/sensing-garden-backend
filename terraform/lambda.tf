# Archive the Lambda source code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/src"
  output_path = "${path.module}/../lambda/deployment_package.zip"
}

resource "aws_lambda_function" "write_data" {
  function_name    = "write-data-function"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "handler.handler"
  runtime         = "python3.9"
  filename        = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout         = 10
  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.sensor_detections.name
      S3_BUCKET_NAME = aws_s3_bucket.sensor_images.id
    }
  }
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

# Permission for API Gateway to invoke Lambda
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.write_data.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*/data"
}