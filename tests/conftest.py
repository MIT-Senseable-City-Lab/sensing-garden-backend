"""
Pytest configuration and fixtures for backend tests.
Sets up test environment to use local AWS services.
"""

import os
import pytest
import boto3
from moto import mock_dynamodb, mock_s3
from dotenv import load_dotenv

# Load test environment
load_dotenv('.env.local')

# Ensure we're in local/test mode
os.environ['ENVIRONMENT'] = 'local'
os.environ['AWS_ENDPOINT_URL'] = 'http://localhost:4566'

@pytest.fixture(scope='session')
def aws_credentials():
    """Mocked AWS Credentials for moto/testing"""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

@pytest.fixture(scope='function')
def dynamodb_tables(aws_credentials):
    """Create DynamoDB tables for testing"""
    with mock_dynamodb():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create all required tables
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
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            },
            {
                'TableName': 'sensing-garden-devices',
                'KeySchema': [
                    {'AttributeName': 'device_id', 'KeyType': 'HASH'}
                ],
                'AttributeDefinitions': [
                    {'AttributeName': 'device_id', 'AttributeType': 'S'}
                ],
                'BillingMode': 'PAY_PER_REQUEST'
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
                ],
                'BillingMode': 'PAY_PER_REQUEST'
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
                ],
                'BillingMode': 'PAY_PER_REQUEST'
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
                ],
                'BillingMode': 'PAY_PER_REQUEST'
            }
        ]
        
        for table_config in tables:
            dynamodb.create_table(**table_config)
        
        yield dynamodb

@pytest.fixture(scope='function')
def s3_buckets(aws_credentials):
    """Create S3 buckets for testing"""
    with mock_s3():
        s3 = boto3.client('s3', region_name='us-east-1')
        
        # Create test buckets
        s3.create_bucket(Bucket='test-sensing-garden-images')
        s3.create_bucket(Bucket='test-sensing-garden-videos')
        
        yield s3

@pytest.fixture
def api_event():
    """Create a mock API Gateway event"""
    def _create_event(method='GET', path='/', body=None, query_params=None, headers=None):
        event = {
            'requestContext': {
                'http': {
                    'method': method,
                    'path': path
                }
            },
            'headers': headers or {},
            'queryStringParameters': query_params or {},
            'body': body
        }
        return event
    
    return _create_event

@pytest.fixture
def lambda_context():
    """Create a mock Lambda context"""
    class Context:
        function_name = 'test-lambda'
        function_version = '$LATEST'
        invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-lambda'
        memory_limit_in_mb = 256
        aws_request_id = 'test-request-id'
        log_group_name = '/aws/lambda/test-lambda'
        log_stream_name = 'test-stream'
        
        def get_remaining_time_in_millis(self):
            return 30000
    
    return Context()