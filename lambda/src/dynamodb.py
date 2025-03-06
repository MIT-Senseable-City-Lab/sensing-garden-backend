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
    """Load the JSON schema for validation"""
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.json')
    with open(schema_path, 'r') as f:
        return json.load(f)

def _validate_data(data, table_type):
    """Generic validation function for both detection and classification data"""
    schema = _load_schema()
    db_schema = schema['db'][table_type]
    
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
                
            # Float validation and conversion to Decimal
            elif field_type == 'float':
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