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
    """Load the JSON schema for validation from a relative path"""
    try:
        # First try to look for schema in the deployed Lambda environment
        schema_path = os.path.join('/opt', 'schema.json')
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Could not load schema from Lambda layer: {str(e)}")
    
    try:
        # Fall back to loading from common directory during local development
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        schema_path = os.path.join(base_dir, 'common', 'schema.json')
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not load schema from common directory: {str(e)}")
        # As a last resort, return a basic schema
        return {
            "properties": {
                "db": {
                    "properties": {
                        "sensor_detections": {
                            "required": ["device_id", "timestamp", "model_id", "image_key", "image_bucket"],
                            "properties": {}
                        },
                        "sensor_classifications": {
                            "required": ["device_id", "timestamp", "model_id", "image_key", "image_bucket", 
                                       "family", "genus", "species", "family_confidence", "genus_confidence", "species_confidence"],
                            "properties": {}
                        }
                    }
                },
                "api": {
                    "properties": {
                        "detection_request": {
                            "required": ["device_id", "model_id", "image"],
                            "properties": {}
                        },
                        "classification_request": {
                            "required": ["device_id", "model_id", "image", "family", "genus", "species", 
                                        "family_confidence", "genus_confidence", "species_confidence"],
                            "properties": {}
                        }
                    }
                }
            }
        }

# Load the schema once
DB_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'common', 'db-schema.json')
with open(DB_SCHEMA_PATH, 'r') as f:
    DB_SCHEMA = json.load(f)

def _validate_data(data, table_type):
    """Generic validation function for both detection and classification data"""
    db_schema = DB_SCHEMA['properties'][table_type]
    
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