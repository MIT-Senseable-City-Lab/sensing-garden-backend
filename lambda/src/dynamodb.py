import json
import os
from decimal import Decimal

import boto3


# Custom JSON encoder to handle DynamoDB data types
class DynamoDBEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, list) and all(isinstance(x, (int, float, Decimal)) for x in obj):
            return [float(x) if isinstance(x, Decimal) else x for x in obj]
        return super(DynamoDBEncoder, self).default(obj)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Table names
DETECTIONS_TABLE = 'sensing-garden-detections'
CLASSIFICATIONS_TABLE = 'sensing-garden-classifications'
MODELS_TABLE = 'sensing-garden-models'
VIDEOS_TABLE = 'sensing-garden-videos'
DEVICES_TABLE = 'sensing-garden-devices'

import traceback

def add_device(device_id: str, created: str = None):
    """Add a device to the devices table."""
    table = dynamodb.Table(DEVICES_TABLE)
    result = {'statusCode': 500, 'body': json.dumps({'error': 'Unknown error'})}
    if not device_id:
        result = {'statusCode': 400, 'body': json.dumps({'error': 'device_id is required'})}
        return result
    item = {'device_id': device_id}
    if created:
        item['created'] = created
    else:
        from datetime import datetime, timezone
        item['created'] = datetime.now(timezone.utc).isoformat()
    try:
        table.put_item(Item=item)
        result = {'statusCode': 200, 'body': json.dumps({'message': 'Device added', 'device': item}, cls=DynamoDBEncoder)}
    except Exception as e:
        print(f"[add_device] ERROR: {str(e)}")
        result = {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
    return result

def delete_device(device_id: str):
    """Delete a device from the devices table by device_id."""
    table = dynamodb.Table(DEVICES_TABLE)
    result = {'statusCode': 500, 'body': json.dumps({'error': 'Unknown error'})}
    if not device_id:
        result = {'statusCode': 400, 'body': json.dumps({'error': 'device_id is required'})}
        return result
    try:
        table.delete_item(Key={'device_id': device_id})
        result = {'statusCode': 200, 'body': json.dumps({'message': 'Device deleted', 'device_id': device_id}, cls=DynamoDBEncoder)}
    except Exception as e:
        print(f"[delete_device] ERROR: {str(e)}")
        result = {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
    return result

def get_devices(device_id: str = None, created: str = None, limit: int = 100, next_token: str = None, sort_by: str = None, sort_desc: bool = False):
    """Query devices table with optional filters and pagination."""
    from boto3.dynamodb.conditions import Key, Attr
    table = dynamodb.Table(DEVICES_TABLE)
    base_params = {}
    try:
        base_params['Limit'] = min(limit, 100) if limit else 100
        if next_token:
            try:
                base_params['ExclusiveStartKey'] = json.loads(next_token)
            except json.JSONDecodeError:
                raise ValueError('Invalid next_token format')
        filter_expressions = []
        if device_id:
            filter_expressions.append(Attr('device_id').eq(device_id))
        if created:
            filter_expressions.append(Attr('created').eq(created))
        if filter_expressions:
            combined_filter = filter_expressions[0]
            for expr in filter_expressions[1:]:
                combined_filter = combined_filter & expr
            base_params['FilterExpression'] = combined_filter
        # Only set projection if both fields are known to exist
        base_params['ProjectionExpression'] = "device_id, created"
        print(f"[get_devices] SCAN params: {base_params}")
        response = table.scan(**base_params)
        items = response.get('Items', [])
        if sort_by and items:
            if any(sort_by in item for item in items):
                reverse_sort = bool(sort_desc)
                items = sorted(
                    items,
                    key=lambda x: (sort_by in x, x.get(sort_by)),
                    reverse=reverse_sort
                )
                print(f"[get_devices] Sorted {len(items)} items by {sort_by} in {'descending' if reverse_sort else 'ascending'} order")
        result = {
            'items': items,
            'next_token': json.dumps(response.get('LastEvaluatedKey')) if response.get('LastEvaluatedKey') else None
        }
        return result
    except Exception as e:
        print(f"[get_devices] ERROR: {str(e)}\n{traceback.format_exc()}")
        return {'items': [], 'next_token': None, 'error': str(e), 'traceback': traceback.format_exc()}

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
            'classification': 'sensor_classifications',
            'video': 'videos'
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
                
                # Array validation for bounding_box: must be [xmin, ymin, xmax, ymax]
                elif field == "bounding_box" and isinstance(value, list):
                    if len(value) != 4:
                        error_msg = f"Bounding box must be a list of 4 numbers [xmin, ymin, xmax, ymax], got {value}"
                        print(error_msg)
                        return False, error_msg
                    if not all(isinstance(coord, (int, float, Decimal)) for coord in value):
                        error_msg = f"All bounding box coordinates should be numbers, got {value}"
                        print(error_msg)
                        return False, error_msg
                    xmin, ymin, xmax, ymax = value
                    if not (xmin < xmax and ymin < ymax):
                        error_msg = f"Bounding box coordinates must satisfy xmin < xmax and ymin < ymax, got {value}"
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
    
    try:
        # Use query instead of get_item since we have a composite key
        from boto3.dynamodb.conditions import Key
        
        response = models_table.query(
            KeyConditionExpression=Key('id').eq(model_id)
        )
        
        if not response.get('Items'):
            error_msg = f"Model with id '{model_id}' not found in models table"
            print(error_msg)
            return False, error_msg
        
        return True, ""
    except Exception as e:
        error_msg = f"Error validating model_id: {str(e)}"
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
            raise ValueError(f"Invalid model_id: {model_error}")
    
    # Store in DynamoDB
    table = dynamodb.Table(table_name)
    table.put_item(Item=data)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'{data_type.replace("sensor_", "").capitalize()} data stored successfully',
            'data': data
        }, cls=DynamoDBEncoder)
    }

def store_detection_data(data):
    """Store sensor detection data in DynamoDB"""
    return _store_data(data, DETECTIONS_TABLE, 'detection')

def store_classification_data(data):
    """Store sensor classification data in DynamoDB"""
    return _store_data(data, CLASSIFICATIONS_TABLE, 'classification')

def store_model_data(data):
    """Store model data in DynamoDB"""
    # Models must have an id field which is the primary key
    if 'id' not in data:
        raise ValueError("Model data must contain an 'id' field")
        
    # Set the type field which is required by the schema
    if 'type' not in data:
        data['type'] = 'model'  # Default type
        
    return _store_data(data, MODELS_TABLE, 'model')

def store_video_data(data):
    """Store video data in DynamoDB"""
    # Set the type field which is required by the schema
    if 'type' not in data:
        data['type'] = 'video'  # Default type
        
    return _store_data(data, VIDEOS_TABLE, 'video')

def count_data(table_type: str, device_id: str = None, model_id: str = None, start_time: str = None, end_time: str = None):
    """Count items in DynamoDB with filtering (efficiently using Select='COUNT')"""
    if table_type not in ['detection', 'classification', 'model', 'video']:
        raise ValueError(f"Invalid table_type: {table_type}")
    
    table_name = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE,
        'video': VIDEOS_TABLE
    }[table_type]
    table = dynamodb.Table(table_name)
    from boto3.dynamodb.conditions import Key, Attr
    query_params = {
        'Select': 'COUNT'
    }
    # Filtering logic (same as query_data)
    key_condition = None
    filter_expression = None
    if table_type in ['detection', 'classification', 'video']:
        if device_id:
            key_condition = Key('device_id').eq(device_id)
        if start_time and end_time:
            if key_condition is not None:
                key_condition = key_condition & Key('timestamp').between(start_time, end_time)
            else:
                key_condition = Key('timestamp').between(start_time, end_time)
        elif start_time:
            if key_condition is not None:
                key_condition = key_condition & Key('timestamp').gte(start_time)
            else:
                key_condition = Key('timestamp').gte(start_time)
        elif end_time:
            if key_condition is not None:
                key_condition = key_condition & Key('timestamp').lte(end_time)
            else:
                key_condition = Key('timestamp').lte(end_time)
        if key_condition is not None:
            query_params['KeyConditionExpression'] = key_condition
        if model_id and table_type in ['detection', 'classification']:
            filter_expression = Attr('model_id').eq(model_id)
            query_params['FilterExpression'] = filter_expression
        response = table.query(**query_params) if 'KeyConditionExpression' in query_params else table.scan(**query_params)
    elif table_type == 'model':
        # Models table: primary key is 'id', so we have to scan for device_id/model_id
        filter_expression = None
        if device_id:
            filter_expression = Attr('device_id').eq(device_id)
        if model_id:
            if filter_expression is not None:
                filter_expression = filter_expression & Attr('id').eq(model_id)
            else:
                filter_expression = Attr('id').eq(model_id)
        if start_time:
            if filter_expression is not None:
                filter_expression = filter_expression & Attr('timestamp').gte(start_time)
            else:
                filter_expression = Attr('timestamp').gte(start_time)
        if end_time:
            if filter_expression is not None:
                filter_expression = filter_expression & Attr('timestamp').lte(end_time)
            else:
                filter_expression = Attr('timestamp').lte(end_time)
        if filter_expression is not None:
            query_params['FilterExpression'] = filter_expression
        response = table.scan(**query_params)
    else:
        response = table.scan(**query_params)
    count = response.get('Count', 0)
    # If paginated, sum all pages
    while 'LastEvaluatedKey' in response:
        if 'KeyConditionExpression' in query_params:
            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = table.query(**query_params)
        else:
            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = table.scan(**query_params)
        count += response.get('Count', 0)
    return {'count': count}

def query_data(table_type: str, device_id: str = None, model_id: str = None, start_time: str = None, 
               end_time: str = None, limit: int = 100, next_token: str = None, 
               sort_by: str = None, sort_desc: bool = False):
    """Query data from DynamoDB with filtering and pagination"""
    if table_type not in ['detection', 'classification', 'model', 'video']:
        raise ValueError(f"Invalid table_type: {table_type}")
    
    table_name = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE,
        'video': VIDEOS_TABLE
    }[table_type]
    
    table = dynamodb.Table(table_name)
    
    # Validate model_id if it's provided and we're querying detections or classifications
    if table_type in ['detection', 'classification'] and model_id:
        model_exists, error = _validate_model_exists(model_id)
        if not model_exists:
            raise ValueError(f"Invalid model_id: {error}")
    
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
                query_params['FilterExpression'] = Attr('id').eq(model_id)
                
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
                filter_expressions.append(Attr('id').eq(model_id))
                
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