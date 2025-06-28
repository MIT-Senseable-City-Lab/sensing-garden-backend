#!/usr/bin/env python3
"""
Setup script for local development environment using LocalStack.
Creates all necessary AWS resources locally without touching production.
"""

import os
import sys
import time
import boto3
import json
from botocore.exceptions import ClientError

# LocalStack endpoint
LOCALSTACK_ENDPOINT = os.environ.get('AWS_ENDPOINT_URL', 'http://localhost:4566')

# Configure boto3 for LocalStack
def get_client(service):
    return boto3.client(
        service,
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )

def wait_for_localstack():
    """Wait for LocalStack to be ready"""
    print("Waiting for LocalStack to be ready...")
    max_retries = 30
    for i in range(max_retries):
        try:
            s3 = get_client('s3')
            s3.list_buckets()
            print("LocalStack is ready!")
            return True
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print(f"LocalStack not ready after {max_retries} attempts")
                return False

def create_dynamodb_tables():
    """Create DynamoDB tables for local development"""
    dynamodb = get_client('dynamodb')
    
    tables = [
        {
            'TableName': 'sensing-garden-detections',
            'KeySchema': [
                {'AttributeName': 'device_id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'device_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ]
        },
        {
            'TableName': 'sensing-garden-devices',
            'KeySchema': [
                {'AttributeName': 'device_id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'device_id', 'AttributeType': 'S'}
            ]
        },
        {
            'TableName': 'sensing-garden-classifications',
            'KeySchema': [
                {'AttributeName': 'device_id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'device_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'},
                {'AttributeName': 'species', 'AttributeType': 'S'}
            ],
            'LocalSecondaryIndexes': [
                {
                    'IndexName': 'species-index',
                    'KeySchema': [
                        {'AttributeName': 'device_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'species', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ]
        },
        {
            'TableName': 'sensing-garden-models',
            'KeySchema': [
                {'AttributeName': 'model_name', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'model_name', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ]
        },
        {
            'TableName': 'sensing-garden-videos',
            'KeySchema': [
                {'AttributeName': 'device_id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'device_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ]
        }
    ]
    
    for table_config in tables:
        try:
            print(f"Creating DynamoDB table: {table_config['TableName']}")
            
            # Add common parameters
            table_config['BillingMode'] = 'PAY_PER_REQUEST'
            
            dynamodb.create_table(**table_config)
            print(f"✓ Created table: {table_config['TableName']}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                print(f"Table {table_config['TableName']} already exists")
            else:
                print(f"Error creating table {table_config['TableName']}: {e}")

def create_s3_buckets():
    """Create S3 buckets for local development"""
    s3 = get_client('s3')
    
    # Note: Using different bucket names for local to avoid conflicts
    buckets = [
        'local-sensing-garden-images',
        'local-sensing-garden-videos'
    ]
    
    for bucket in buckets:
        try:
            print(f"Creating S3 bucket: {bucket}")
            s3.create_bucket(Bucket=bucket)
            
            # Configure CORS
            cors_config = {
                'CORSRules': [{
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                    'AllowedOrigins': ['*'],
                    'ExposeHeaders': ['ETag'],
                    'MaxAgeSeconds': 3000
                }]
            }
            s3.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_config)
            
            print(f"✓ Created bucket: {bucket}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyExists':
                print(f"Bucket {bucket} already exists")
            else:
                print(f"Error creating bucket {bucket}: {e}")

def create_test_data():
    """Create some test data for local development"""
    dynamodb = get_client('dynamodb')
    
    # Add a test device
    try:
        print("Adding test device...")
        dynamodb.put_item(
            TableName='sensing-garden-devices',
            Item={
                'device_id': {'S': 'test-device-001'},
                'name': {'S': 'Test Garden Device'},
                'location': {'S': 'Local Test Environment'},
                'created_at': {'S': '2024-01-01T00:00:00Z'}
            }
        )
        print("✓ Added test device")
    except Exception as e:
        print(f"Error adding test data: {e}")

def main():
    """Main setup function"""
    print("=== Sensing Garden Local Environment Setup ===")
    print(f"LocalStack endpoint: {LOCALSTACK_ENDPOINT}")
    
    if not wait_for_localstack():
        sys.exit(1)
    
    print("\nCreating AWS resources...")
    create_dynamodb_tables()
    create_s3_buckets()
    create_test_data()
    
    print("\n✓ Local environment setup complete!")
    print("\nLocal AWS services available at:")
    print(f"  - DynamoDB: {LOCALSTACK_ENDPOINT}")
    print(f"  - S3: {LOCALSTACK_ENDPOINT}")
    print("\nTo use the local environment, set:")
    print(f"  export AWS_ENDPOINT_URL={LOCALSTACK_ENDPOINT}")
    print("  export AWS_ACCESS_KEY_ID=test")
    print("  export AWS_SECRET_ACCESS_KEY=test")

if __name__ == '__main__':
    main()