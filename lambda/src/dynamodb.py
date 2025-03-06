import json
import os
import boto3
from datetime import datetime

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

def load_schema():
    """Load the JSON schema for validation"""
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.json')
    with open(schema_path, 'r') as f:
        return json.load(f)

def validate_sensor_data(data):
    """Validate sensor data against schema
    
    Args:
        data (dict): The sensor data to validate
        
    Returns:
        bool: True if data matches schema, False otherwise
    """
    schema = load_schema()
    required_fields = schema['sensor_detections'].keys()
    
    # Check if all required fields are present
    for field in required_fields:
        if field not in data:
            return False
            
    # Check field types
    field_types = schema['sensor_detections']
    for field, value in data.items():
        if field not in field_types:
            return False
        expected_type = field_types[field]
        if expected_type == 'string' and not isinstance(value, str):
            return False
    
    return True

def store_sensor_data(data):
    """Validate and store sensor data in DynamoDB
    
    Args:
        data (dict): The sensor data to validate and store
        
    Returns:
        dict: The stored item
        
    Raises:
        ValueError: If data doesn't match schema
        botocore.exceptions.ClientError: If DynamoDB operation fails
    """
    # Validate against schema
    if not validate_sensor_data(data):
        raise ValueError("Data does not match schema")
    
    # Store in DynamoDB
    response = table.put_item(Item=data)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Data stored successfully',
            'data': data
        })
    }