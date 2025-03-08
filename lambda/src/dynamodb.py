import json
import os
import boto3
from decimal import Decimal

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Table names
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'

def _load_schema():
    """Load the JSON schema for validation from the common directory"""
    # Navigate up from lambda/src to the common directory
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    schema_path = os.path.join(base_dir, 'common', 'schema.json')
    with open(schema_path, 'r') as f:
        return json.load(f)

# Load the schema once
SCHEMA = _load_schema()

def _validate_data(data, table_type):
    """Generic validation function for both detection and classification data"""
    db_schema = SCHEMA['properties']['db']['properties'][table_type]
    
    # Check required fields
    missing_fields = [field for field in db_schema['required'] if field not in data]
    if missing_fields:
        print(f"Missing required fields: {', '.join(missing_fields)}")
        return False
    
    # Check field types
    for field, value in data.items():
        if field in db_schema['properties']:
            field_type = db_schema['properties'][field]['type']
            
            # String validation
            if field_type == 'string' and not isinstance(value, str):
                print(f"Field {field} should be a string, got {type(value)}")
                return False
                
            # Number validation and conversion to Decimal
            elif field_type == 'number':
                try:
                    if not isinstance(value, Decimal):
                        if isinstance(value, str):
                            data[field] = Decimal(value)
                        elif isinstance(value, (float, int)):
                            data[field] = Decimal(str(value))
                        else:
                            print(f"Field {field} should be a number, got {type(value)}")
                            return False
                except (ValueError, TypeError):
                    print(f"Could not convert {field} to Decimal: {value}")
                    return False
    
    return True

def _store_data(data, table_name, data_type):
    """Generic function to store data in DynamoDB"""
    # Validate against schema
    if not _validate_data(data, data_type):
        raise ValueError(f"{data_type} data does not match schema")
    
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
    return _store_data(data, DETECTIONS_TABLE, 'sensor_detections')

def store_classification_data(data):
    """Store sensor classification data in DynamoDB"""
    return _store_data(data, CLASSIFICATIONS_TABLE, 'sensor_classifications')