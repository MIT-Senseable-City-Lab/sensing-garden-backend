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
        
        # Map table types to schema keys (handling singular/plural mismatch)
        schema_type_mapping = {
            'model': 'models',
            'detection': 'sensor_detections',
            'classification': 'sensor_classifications'
        }
        
        # Use mapped schema key if available
        schema_key = schema_type_mapping.get(table_type, table_type)
        
        # Check schema existence
        if schema_key not in SCHEMA['properties']:
            error_msg = f"Schema for {table_type} not found in DB schema (looked for '{schema_key}')"
            print(error_msg)
            return False, error_msg
        
        # Use the mapped schema key to get the schema properties
        db_schema = SCHEMA['properties'][schema_key]
        
        # Print schema info for debugging
        print(f"Schema required fields: {db_schema.get('required', [])}")
        print(f"Schema properties: {list(db_schema.get('properties', {}).keys())}")
        
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
                
                # Array validation for bounding_box
                elif field == "bounding_box" and isinstance(value, list):
                    if not all(isinstance(coord, (int, float, Decimal)) for coord in value):
                        error_msg = f"All bounding box coordinates should be numbers, got {value}"
                        print(error_msg)
                        return False, error_msg
                    
                    # Convert all coordinates to Decimal for DynamoDB compatibility
                    try:
                        for i, coord in enumerate(value):
                            if not isinstance(coord, Decimal):
                                data[field][i] = Decimal(str(coord))
                    except (ValueError, TypeError) as e:
                        error_msg = f"Could not convert bounding_box coordinates to Decimal: {value}. Error: {str(e)}"
                        print(error_msg)
                        return False, error_msg
                elif field == "bounding_box":
                    error_msg = f"Field bounding_box should be an array of numbers, got {type(value)}"
                    print(error_msg)
                    return False, error_msg
        
        return True, ""
    except Exception as e:
        error_msg = f"Unexpected error in validation: {str(e)}"
        print(error_msg)
        return False, error_msg

def _validate_model_exists(model_id):
    """Validate that a model_id exists in the models table"""
    if not model_id:
        return True, ""  # No model_id to validate
    
    print(f"Validating model_id exists: {model_id}")
    models_table = dynamodb.Table(MODELS_TABLE)
    
    # First try to get the model by model_id as the primary key (id)
    try:
        response = models_table.get_item(
            Key={
                'id': model_id
            }
        )
        
        # If the model exists with id=model_id, return true
        if 'Item' in response:
            return True, ""
    except Exception as e:
        print(f"Error while checking model by id: {str(e)}")
    
    # If not found by id, use scan to check if any model has this model_id
    try:
        from boto3.dynamodb.conditions import Attr
        
        scan_response = models_table.scan(
            FilterExpression=Attr('model_id').eq(model_id)
        )
        
        # If at least one item was found, the model exists
        if scan_response.get('Items', []):
            return True, ""
    except Exception as e:
        print(f"Error while scanning for model_id: {str(e)}")
    
    # If we got here, the model doesn't exist
    error_msg = f"Model with id '{model_id}' not found in models table"
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
    
    # For detection and classification, validate that model_id exists if provided
    if data_type in ['detection', 'classification'] and 'model_id' in data:
        model_exists, model_error = _validate_model_exists(data['model_id'])
        if not model_exists:
            detailed_error = f"{data_type} data references invalid model_id: {model_error}"
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
    # For models table, make sure to map device_id to id (the primary key)
    if 'device_id' in data and 'id' not in data:
        data['id'] = data['device_id']
        
    # Set the type field which is required by the schema
    if 'type' not in data:
        data['type'] = 'model'  # Default type
        
    return _store_data(data, MODELS_TABLE, 'model')

def query_data(table_type: str, device_id: str = None, model_id: str = None, start_time: str = None, 
               end_time: str = None, limit: int = 100, next_token: str = None, 
               sort_by: str = None, sort_desc: bool = False):
    """Query data from DynamoDB with filtering and pagination"""
    # Map table type to actual table name
    table_mapping = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE
    }
    
    if table_type not in table_mapping:
        raise ValueError(f'Invalid table type: {table_type}')
    
    # Print debugging info to CloudWatch
    print(f"Querying {table_type} with params: device_id={device_id}, model_id={model_id}, start_time={start_time}, end_time={end_time}")
    
    table = dynamodb.Table(table_mapping[table_type])
    
    # Import conditions for expressions
    from boto3.dynamodb.conditions import Key, Attr
    
    # Base parameters - will be different for query vs scan
    base_params = {
        'Limit': min(limit, 100) if limit else 100  # Cap at 100 items per request
    }
    
    # Add pagination token if provided
    if next_token:
        try:
            base_params['ExclusiveStartKey'] = json.loads(next_token)
        except json.JSONDecodeError:
            raise ValueError('Invalid next_token format')
    
    # Handle different table schemas (models table uses 'id' as hash key, others use 'device_id')
    if table_type == 'model':
        # For models table
        if device_id:  # In models table, we use device_id as the 'id' field
            # QUERY operation - can use KeyConditionExpression
            query_params = base_params.copy()
            
            # Create key condition for id (using device_id as the value)
            key_condition = Key('id').eq(device_id)
            
            # Add time range conditions if provided
            if start_time and end_time:
                key_condition = key_condition & Key('timestamp').between(start_time, end_time)
            elif start_time:
                key_condition = key_condition & Key('timestamp').gte(start_time)
            elif end_time:
                key_condition = key_condition & Key('timestamp').lte(end_time)
                
            query_params['KeyConditionExpression'] = key_condition
            
            # Add model_id as a filter if provided (in models table, model_id might be a different attribute)
            if model_id:
                query_params['FilterExpression'] = Attr('model_id').eq(model_id)
                
            # Execute query
            print(f"Executing QUERY on models table with params: {query_params}")
            response = table.query(**query_params)
        else:
            # SCAN operation for models table
            scan_params = base_params.copy()
            filter_expressions = []
            
            # Add time range as filter expressions
            if start_time:
                filter_expressions.append(Attr('timestamp').gte(start_time))
            if end_time:
                filter_expressions.append(Attr('timestamp').lte(end_time))
            if model_id:
                filter_expressions.append(Attr('model_id').eq(model_id))
                
            # Combine filter expressions if any exist
            if filter_expressions:
                combined_filter = filter_expressions[0]
                for expr in filter_expressions[1:]:
                    combined_filter = combined_filter & expr
                scan_params['FilterExpression'] = combined_filter
                
            # Execute scan
            print(f"Executing SCAN on models table with params: {scan_params}")
            response = table.scan(**scan_params)
    else:
        # For detections and classifications tables which use device_id as hash key
        if device_id:
            # QUERY operation - can use KeyConditionExpression
            query_params = base_params.copy()
            
            # Create key condition for device_id
            key_condition = Key('device_id').eq(device_id)
            
            # Add time range conditions if provided
            if start_time and end_time:
                key_condition = key_condition & Key('timestamp').between(start_time, end_time)
            elif start_time:
                key_condition = key_condition & Key('timestamp').gte(start_time)
            elif end_time:
                key_condition = key_condition & Key('timestamp').lte(end_time)
                
            query_params['KeyConditionExpression'] = key_condition
            
            # Add model_id as a filter if provided
            if model_id:
                query_params['FilterExpression'] = Attr('model_id').eq(model_id)
                
            # Execute query
            print(f"Executing QUERY with params: {query_params}")
            response = table.query(**query_params)
        else:
            # SCAN operation - must use FilterExpression, cannot use KeyConditionExpression
            scan_params = base_params.copy()
            filter_expressions = []
            
            # Add time range as filter expressions
            if start_time:
                filter_expressions.append(Attr('timestamp').gte(start_time))
            if end_time:
                filter_expressions.append(Attr('timestamp').lte(end_time))
            if model_id:
                filter_expressions.append(Attr('model_id').eq(model_id))
                
            # Combine filter expressions if any exist
            if filter_expressions:
                combined_filter = filter_expressions[0]
                for expr in filter_expressions[1:]:
                    combined_filter = combined_filter & expr
                scan_params['FilterExpression'] = combined_filter
                
            # Execute scan
            print(f"Executing SCAN with params: {scan_params}")
            response = table.scan(**scan_params)
    
    # Format response
    items = response.get('Items', [])
    
    # Sort items if sort_by is specified
    if sort_by and items:
        # Check if the attribute exists in the items
        if any(sort_by in item for item in items):
            # Use sort_desc directly for determining sort direction
            # Set default to False (ascending) if not specified
            reverse_sort = bool(sort_desc)
                
            # Sort items, handling missing attributes gracefully
            # Items missing the sort attribute will appear last in ascending order
            # and first in descending order
            items = sorted(
                items,
                key=lambda x: (sort_by in x, x.get(sort_by)),
                reverse=reverse_sort
            )
            print(f"Sorted {len(items)} items by {sort_by} in {'descending' if reverse_sort else 'ascending'} order")
    
    result = {
        'items': items,
        'count': len(items)
    }
    
    # Add pagination token if more results exist
    if 'LastEvaluatedKey' in response:
        result['next_token'] = json.dumps(response['LastEvaluatedKey'])
    
    return result