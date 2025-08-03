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
ENVIRONMENTAL_READINGS_TABLE = 'sensing-garden-environmental-readings'

import traceback

from typing import Dict, Any, Optional

def add_device(device_id: str, created: Optional[str] = None) -> Dict[str, Any]:
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

def store_device_if_not_exists(device_id: str) -> Dict[str, Any]:
    """
    Check if a device exists in the devices table. If not, add it. Idempotent.
    """
    if not device_id:
        raise ValueError("device_id is required")
    table = dynamodb.Table(DEVICES_TABLE)
    try:
        response = table.get_item(Key={'device_id': device_id})
        if 'Item' in response and response['Item'].get('device_id') == device_id:
            # Device already exists
            return {'statusCode': 200, 'body': json.dumps({'message': 'Device already exists', 'device_id': device_id})}
        # Device does not exist, add it
        return add_device(device_id)
    except Exception as e:
        print(f"[store_device_if_not_exists] ERROR: {str(e)}")
        raise

    """
    Check if a device exists in the devices table. If not, add it. Idempotent.
    """
    if not device_id:
        raise ValueError("device_id is required")
    table = dynamodb.Table(DEVICES_TABLE)
    try:
        response = table.get_item(Key={'device_id': device_id})
        if 'Item' in response and response['Item'].get('device_id') == device_id:
            # Device already exists
            return {'statusCode': 200, 'body': json.dumps({'message': 'Device already exists', 'device_id': device_id})}
        # Device does not exist, add it
        return add_device(device_id)
    except Exception as e:
        print(f"[store_device_if_not_exists] ERROR: {str(e)}")
        raise

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

def delete_device(device_id: str) -> Dict[str, Any]:
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

def get_devices(device_id: Optional[str] = None, created: Optional[str] = None, limit: int = 100, next_token: Optional[str] = None, sort_by: Optional[str] = None, sort_desc: bool = False) -> Dict[str, Any]:
    """Query devices table with optional filters and pagination."""
    from boto3.dynamodb.conditions import Key, Attr
    table = dynamodb.Table(DEVICES_TABLE)
    base_params = {}
    try:
        base_params['Limit'] = min(limit, 5000) if limit else 100
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

def _load_schema() -> Dict[str, Any]:
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

def _validate_data(data: Dict[str, Any], table_type: str) -> (bool, str):
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
            'video': 'videos',
            'environmental_reading': 'environmental_readings'
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


def _store_data(data: Dict[str, Any], table_name: str, data_type: str) -> Dict[str, Any]:
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

def store_environmental_data(data):
    """Store environmental reading data in DynamoDB"""
    return _store_data(data, ENVIRONMENTAL_READINGS_TABLE, 'environmental_reading')

def query_environmental_data(device_id: Optional[str] = None, start_time: Optional[str] = None,
                           end_time: Optional[str] = None, limit: int = 100, next_token: Optional[str] = None,
                           sort_by: Optional[str] = None, sort_desc: bool = False) -> Dict[str, Any]:
    """Query environmental readings data with filtering and pagination."""
    return query_data('environmental_reading', device_id, None, start_time, end_time, limit, next_token, sort_by, sort_desc)

def count_environmental_data(device_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
    """Count environmental readings with filtering."""
    return count_data('environmental_reading', device_id, None, start_time, end_time)

def count_data(table_type: str, device_id: Optional[str] = None, model_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
    """Count items in DynamoDB with filtering (efficiently using Select='COUNT')"""
    if table_type not in ['detection', 'classification', 'model', 'video', 'environmental_reading']:
        raise ValueError(f"Invalid table_type: {table_type}")
    
    table_name = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE,
        'video': VIDEOS_TABLE,
        'environmental_reading': ENVIRONMENTAL_READINGS_TABLE
    }[table_type]
    table = dynamodb.Table(table_name)
    from boto3.dynamodb.conditions import Key, Attr
    query_params = {
        'Select': 'COUNT'
    }
    # Filtering logic (same as query_data)
    key_condition = None
    filter_expression = None
    if table_type in ['detection', 'classification', 'video', 'environmental_reading']:
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

def query_data(table_type: str, device_id: Optional[str] = None, model_id: Optional[str] = None, start_time: Optional[str] = None,
               end_time: Optional[str] = None, limit: int = 100, next_token: Optional[str] = None,
               sort_by: Optional[str] = None, sort_desc: bool = False) -> Dict[str, Any]:
    """Unified query for all DynamoDB tables with filtering and pagination."""
    if table_type not in ['detection', 'classification', 'model', 'video', 'environmental_reading']:
        raise ValueError(f"Invalid table_type: {table_type}")

    table_name = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE,
        'video': VIDEOS_TABLE,
        'environmental_reading': ENVIRONMENTAL_READINGS_TABLE
    }[table_type]
    table = dynamodb.Table(table_name)

    # Partition key per table
    partition_key = {
        'detection': 'device_id',
        'classification': 'device_id',
        'video': 'device_id',
        'environmental_reading': 'device_id',
        'model': 'id'
    }[table_type]
    # model_id field for filtering (optional)
    model_id_field = 'model_id' if table_type in ['detection', 'classification', 'video'] else 'id'


    from boto3.dynamodb.conditions import Key, Attr
    base_params = {'Limit': min(limit, 5000) if limit else 100}
    if next_token:
        try:
            base_params['ExclusiveStartKey'] = json.loads(next_token)
        except json.JSONDecodeError:
            raise ValueError('Invalid next_token format')

    # Use Query if partition key is provided, else Scan
    partition_val = device_id if table_type != 'model' else model_id
    use_query = partition_val is not None
    filter_expressions = []
    key_condition = None
    if use_query:
        key_condition = Key(partition_key).eq(partition_val)
        # Add time range to KeyCondition if possible
        if start_time and end_time:
            key_condition = key_condition & Key('timestamp').between(start_time, end_time)
        elif start_time:
            key_condition = key_condition & Key('timestamp').gte(start_time)
        elif end_time:
            key_condition = key_condition & Key('timestamp').lte(end_time)
    else:
        # Add time range as filter expressions for Scan
        if start_time:
            filter_expressions.append(Attr('timestamp').gte(start_time))
        if end_time:
            filter_expressions.append(Attr('timestamp').lte(end_time))
    # Add model_id/id filter if provided
    if model_id:
        filter_expressions.append(Attr(model_id_field).eq(model_id))
    # Compose filter expression if any
    filter_expr = None
    if filter_expressions:
        filter_expr = filter_expressions[0]
        for expr in filter_expressions[1:]:
            filter_expr = filter_expr & expr
    # Build params
    params = base_params.copy()
    if use_query:
        params['KeyConditionExpression'] = key_condition
        if filter_expr is not None:
            params['FilterExpression'] = filter_expr
        # DynamoDB sort on timestamp when using Query
        if sort_by == 'timestamp':
            # For descending order DynamoDB requires ScanIndexForward=False
            params['ScanIndexForward'] = not bool(sort_desc)
        print(f"Unified QUERY params: {params}")
        response = table.query(**params)
    else:
        if filter_expr is not None:
            params['FilterExpression'] = filter_expr
        print(f"Unified SCAN params: {params}")
        response = table.scan(**params)
    items = response.get('Items', [])
    # Only do in-memory sort for non-videos/models if needed
    if table_type not in ['video', 'model'] and sort_by and items:
        from dateutil.parser import isoparse
        from datetime import datetime, timezone, MINYEAR
        def safe_parse(val):
            try:
                dt = isoparse(val)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except Exception:
                # Always return a datetime for consistent sorting
                # Use datetime.min for ascending, datetime.max for descending
                return datetime.min if not sort_desc else datetime.max
        if any(sort_by in item for item in items):
            reverse_sort = bool(sort_desc)
            if sort_by == "timestamp":
                items = sorted(
                    items,
                    key=lambda x: safe_parse(x.get(sort_by)) if sort_by in x else (datetime.min if not sort_desc else datetime.max),
                    reverse=reverse_sort
                )
            else:
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
    if 'LastEvaluatedKey' in response:
        result['next_token'] = json.dumps(response['LastEvaluatedKey'])
    return result

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

def store_environmental_data(data):
    """Store environmental reading data in DynamoDB"""
    return _store_data(data, ENVIRONMENTAL_READINGS_TABLE, 'environmental_reading')

def query_environmental_data(device_id: Optional[str] = None, start_time: Optional[str] = None,
                           end_time: Optional[str] = None, limit: int = 100, next_token: Optional[str] = None,
                           sort_by: Optional[str] = None, sort_desc: bool = False) -> Dict[str, Any]:
    """Query environmental readings data with filtering and pagination."""
    return query_data('environmental_reading', device_id, None, start_time, end_time, limit, next_token, sort_by, sort_desc)

def count_environmental_data(device_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
    """Count environmental readings with filtering."""
    return count_data('environmental_reading', device_id, None, start_time, end_time)