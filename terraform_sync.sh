#!/bin/bash
# Script to always import AWS resources before running terraform apply
# Usage: ./terraform_sync.sh

set -e

cd "$(dirname "$0")/terraform"

# --- S3 Buckets ---
echo "Importing S3 buckets..."
terraform import aws_s3_bucket.sensor_images scl-sensing-garden-images || true
terraform import aws_s3_bucket.sensor_videos scl-sensing-garden-videos || true

# --- DynamoDB Tables ---
echo "Importing DynamoDB tables..."
terraform import aws_dynamodb_table.sensor_detections sensing-garden-detections || true
terraform import aws_dynamodb_table.devices sensing-garden-devices || true
terraform import aws_dynamodb_table.sensor_classifications sensing-garden-classifications || true
terraform import aws_dynamodb_table.models sensing-garden-models || true
terraform import aws_dynamodb_table.videos sensing-garden-videos || true

# --- API Gateway ---
echo "Importing API Gateway resources..."
# API ID and stage name are derived from Terraform config, but you must supply the real API Gateway ID for first import.
# To find your API Gateway ID, run: aws apigatewayv2 get-apis
API_ID="iwih35j2o8"
STAGE_NAME="$default"
terraform import aws_apigatewayv2_api.http_api "$API_ID" || true
terraform import aws_apigatewayv2_stage.default "$API_ID/$STAGE_NAME" || true

# --- Lambda Function ---
echo "Importing Lambda function..."
terraform import aws_lambda_function.api_handler_function sensing-garden-api-handler || true
# Lambda Layer
terraform import aws_lambda_layer_version.schema_layer schema-layer || true

# --- IAM Roles/Policies ---
echo "Importing IAM roles and policies..."
terraform import aws_iam_role.lambda_exec lambda_exec_role || true
terraform import aws_iam_role_policy.lambda_dynamodb_policy lambda-dynamodb-policy || true
terraform import aws_iam_role_policy.lambda_s3_policy lambda-s3-policy || true

# --- Apply changes ---
echo "Running terraform apply..."
terraform apply -auto-approve
