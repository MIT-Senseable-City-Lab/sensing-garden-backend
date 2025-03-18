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
MODELS_TABLE = 'sensing-garden-models'

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
    return _store_data(data, DETECTIONS_TABLE, 'detection')

def store_classification_data(data):
    """Store sensor classification data in DynamoDB"""
    return _store_data(data, CLASSIFICATIONS_TABLE, 'classification')

def store_model_data(data):
    """Store model data in DynamoDB"""
    return _store_data(data, MODELS_TABLE, 'model')

def query_data(table_type: str, device_id: str = None, model_id: str = None, start_time: str = None, 
               end_time: str = None, limit: int = 100, next_token: str = None):
    """Query data from DynamoDB with filtering and pagination"""
    # Map table type to actual table name
    table_mapping = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE
    }
    
    if table_type not in table_mapping:
        raise ValueError(f'Invalid table type: {table_type}')
    
    table = dynamodb.Table(table_mapping[table_type])
    
    # Base query parameters
    query_params = {
        'Limit': min(limit, 100) if limit else 100  # Cap at 100 items per request
    }
    
    # Add pagination token if provided
    if next_token:
        try:
            query_params['ExclusiveStartKey'] = json.loads(next_token)
        except json.JSONDecodeError:
            raise ValueError('Invalid next_token format')
    
    # Import conditions once for both query and filter expressions
    from boto3.dynamodb.conditions import Key, Attr
    
    # Add device_id filter if provided
    if device_id:
        query_params['KeyConditionExpression'] = Key('device_id').eq(device_id)
        
        # Add time range if provided
        if start_time and end_time:
            query_params['KeyConditionExpression'] &= Key('timestamp').between(start_time, end_time)
        elif start_time:
            query_params['KeyConditionExpression'] &= Key('timestamp').gte(start_time)
        elif end_time:
            query_params['KeyConditionExpression'] &= Key('timestamp').lte(end_time)
    
    # Add model_id filter if provided
    if model_id:
        filter_expression = Attr('model_id').eq(model_id)
        query_params['FilterExpression'] = filter_expression
        
        # Execute query
        response = table.query(**query_params)
    else:
        # If no device_id, use scan
        response = table.scan(**query_params)
    
    # Format response
    result = {
        'items': response.get('Items', []),
        'count': len(response.get('Items', []))
    }
    
    # Add pagination token if more results exist
    if 'LastEvaluatedKey' in response:
        result['next_token'] = json.dumps(response['LastEvaluatedKey'])
    
    return result