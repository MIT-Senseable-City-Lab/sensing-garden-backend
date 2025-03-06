import json
import os
import boto3
from datetime import datetime
from decimal import Decimal

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Hardcoded table names
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'

def _load_schema():
    """Load the JSON schema for validation"""
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.json')
    with open(schema_path, 'r') as f:
        return json.load(f)

def _validate_detection_data(data):
    """Validate detection data against schema
    
    Args:
        data (dict): The detection data to validate
        
    Returns:
        bool: True if data matches schema, False otherwise
    """
    schema = _load_schema()
    schema_type = 'sensor_detections'
    
    # Define required fields for detections
    required_fields = ['device_id', 'model_id', 'timestamp', 's3_image_link']
    
    # Check if all required fields are present
    for field in required_fields:
        if field not in data:
            print(f"Missing required field: {field}")
            return False
            
    # Check field types - be more lenient with types
    for field, value in data.items():
        if field in schema[schema_type] and schema[schema_type][field] == 'string':
            if not isinstance(value, str):
                print(f"Field {field} should be a string, got {type(value)}")
                return False
    
    return True

def _validate_classification_data(data):
    """Validate classification data against schema
    
    Args:
        data (dict): The classification data to validate
        
    Returns:
        bool: True if data matches schema, False otherwise
    """
    schema = _load_schema()
    schema_type = 'sensor_classifications'
    
    # Define required fields for classifications
    required_fields = ['device_id', 'model_id', 'timestamp', 's3_image_link', 'genus', 'family', 'species', 'confidence']
    
    # Check if all required fields are present
    for field in required_fields:
        if field not in data:
            print(f"Missing required field: {field}")
            return False
            
    # Check field types - be more lenient with types
    for field, value in data.items():
        if field in schema[schema_type] and schema[schema_type][field] == 'string':
            if not isinstance(value, str):
                print(f"Field {field} should be a string, got {type(value)}")
                return False
        elif field == 'confidence':
            try:
                # Convert to Decimal for DynamoDB compatibility
                if isinstance(value, str):
                    data[field] = Decimal(value)
                elif isinstance(value, (float, int)):
                    data[field] = Decimal(str(value))
                elif not isinstance(value, Decimal):
                    print(f"Field {field} should be a number, got {type(value)}")
                    return False
            except (ValueError, TypeError):
                print(f"Could not convert {field} to Decimal: {value}")
                return False
    
    return True

def store_detection_data(data):
    """Validate and store sensor detection data in DynamoDB
    
    Args:
        data (dict): The sensor detection data to validate and store
        
    Returns:
        dict: The stored item
        
    Raises:
        ValueError: If data doesn't match schema
        botocore.exceptions.ClientError: If DynamoDB operation fails
    """
    # Validate against schema
    if not _validate_detection_data(data):
        raise ValueError("Detection data does not match schema")
    
    # Store in DynamoDB
    detections_table = dynamodb.Table(DETECTIONS_TABLE)
    response = detections_table.put_item(Item=data)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Detection data stored successfully',
            'data': data
        }, cls=DecimalEncoder)
    }

def store_classification_data(data):
    """Validate and store sensor classification data in DynamoDB
    
    Args:
        data (dict): The sensor classification data to validate and store
        
    Returns:
        dict: The stored item
        
    Raises:
        ValueError: If data doesn't match schema
        botocore.exceptions.ClientError: If DynamoDB operation fails
    """
    # Validate against schema
    if not _validate_classification_data(data):
        raise ValueError("Classification data does not match schema")
    
    # Store in DynamoDB
    classifications_table = dynamodb.Table(CLASSIFICATIONS_TABLE)
    response = classifications_table.put_item(Item=data)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Classification data stored successfully',
            'data': data
        }, cls=DecimalEncoder)
    }