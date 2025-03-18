import json
import os
from decimal import Decimal

import boto3


# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Table names
DETECTIONS_TABLE = 'sensing-garden-detections'
CLASSIFICATIONS_TABLE = 'sensing-garden-classifications'

def _load_schema():
    """Load the DB schema from the appropriate location"""
    try:
        # First try to look for schema in the deployed Lambda environment
        schema_path = os.path.join('/opt', 'db-schema.json')
        if os.path.exists(schema_path):
            print(f"Loading DB schema from Lambda layer: {schema_path}")
            with open(schema_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Could not load schema from Lambda layer: {str(e)}")
    
    # Fall back to loading from common directory during local development
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    schema_path = os.path.join(base_dir, 'common', 'db-schema.json')
    print(f"Loading DB schema from local path: {schema_path}")
    
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        error_msg = f"Failed to load schema from {schema_path}: {str(e)}"
        print(error_msg)
        raise ValueError(error_msg)

# Load the schema once
SCHEMA = _load_schema()

def _validate_data(data, table_type):
    """Generic validation function for both detection and classification data"""
    try:
        # Print debugging info
        print(f"Validating {table_type} data")
        print(f"Available schema keys: {list(SCHEMA['properties'].keys())}")
        print(f"Input data keys: {list(data.keys())}")
        
        # Check schema existence
        if table_type not in SCHEMA['properties']:
            error_msg = f"Schema for {table_type} not found in DB schema"
            print(error_msg)
            return False, error_msg
        
        db_schema = SCHEMA['properties'][table_type]
        
        # Print schema info for debugging
        print(f"Schema required fields: {db_schema.get('required', [])}")
        
        # Check required fields
        required_fields = db_schema.get('required', [])
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            print(error_msg)
            return False, error_msg
        
        # Check field types
        for field, value in data.items():
            if field in db_schema.get('properties', {}):
                field_type = db_schema['properties'][field].get('type')
                
                # String validation
                if field_type == 'string' and not isinstance(value, str):
                    error_msg = f"Field {field} should be a string, got {type(value)}"
                    print(error_msg)
                    return False, error_msg
                    
                # Number validation and conversion to Decimal
                elif field_type == 'number':
                    try:
                        if not isinstance(value, Decimal):
                            if isinstance(value, str):
                                data[field] = Decimal(value)
                            elif isinstance(value, (float, int)):
                                data[field] = Decimal(str(value))
                            else:
                                error_msg = f"Field {field} should be a number, got {type(value)}"
                                print(error_msg)
                                return False, error_msg
                    except (ValueError, TypeError) as e:
                        error_msg = f"Could not convert {field} to Decimal: {value}. Error: {str(e)}"
                        print(error_msg)
                        return False, error_msg
        
        return True, ""
    except Exception as e:
        error_msg = f"Unexpected error in validation: {str(e)}"
        print(error_msg)
        return False, error_msg

def _store_data(data, table_name, data_type):
    """Generic function to store data in DynamoDB"""
    # Validate against schema
    is_valid, error_message = _validate_data(data, data_type)
    if not is_valid:
        detailed_error = f"{data_type} data does not match schema: {error_message}"
        print(detailed_error)
        raise ValueError(detailed_error)
    
    # Store in DynamoDB
    table = dynamodb.Table(table_name)
    table.put_item(Item=data)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'{data_type.replace("sensor_", "").capitalize()} data stored successfully',
            'data': data
        }, cls=DecimalEncoder)
    }

def store_detection_data(data):
    """Store sensor detection data in DynamoDB"""
    return _store_data(data, DETECTIONS_TABLE, 'sensing-garden-detections')

def store_classification_data(data):
    """Store sensor classification data in DynamoDB"""
    return _store_data(data, CLASSIFICATIONS_TABLE, 'sensing-garden-classifications')