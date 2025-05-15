#!/bin/bash
# Script to always import AWS resources before running terraform apply
# Usage: ./terraform_sync.sh

set -e

cd "$(dirname "$0")"

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
# Replace <http_api_id> and <stage_name> with actual values from AWS Console
echo "  (You must fill in the correct IDs below for first-time setup!)"
terraform import aws_apigatewayv2_api.http_api <http_api_id> || true
terraform import aws_apigatewayv2_stage.default <http_api_id>/<stage_name> || true
# Add additional terraform import commands for integrations, routes, keys, usage plans, etc. as needed

# --- Lambda Function ---
echo "Importing Lambda function..."
terraform import aws_lambda_function.api_handler_function sensing-garden-api-handler || true
# Lambda Layer
terraform import aws_lambda_layer_version.schema_layer schema-layer || true
# Lambda Permission (replace <function_name> and <statement_id>)
# terraform import aws_lambda_permission.api_gateway_api_handler <function_name>/<statement_id> || true

# --- IAM Roles/Policies ---
echo "Importing IAM roles and policies..."
terraform import aws_iam_role.lambda_exec lambda_exec_role || true
terraform import aws_iam_role_policy.lambda_dynamodb_policy lambda-dynamodb-policy || true
terraform import aws_iam_role_policy.lambda_s3_policy lambda-s3-policy || true

# --- Apply changes ---
echo "Running terraform apply..."
terraform apply -auto-approve
