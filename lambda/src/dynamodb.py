import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError


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
DEPLOYMENTS_TABLE = 'sensing-garden-deployments'
DEPLOYMENT_DEVICE_CONNECTIONS_TABLE = 'sensing-garden-deployment-device-connections'

import traceback

from typing import Dict, Any, List, Optional

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

def _delete_device_data_from_table(device_id: str, table_name: str) -> int:
    """Delete all items for a device from a specific table using batch operations."""
    from boto3.dynamodb.conditions import Key
    import boto3
    
    table = dynamodb.Table(table_name)
    deleted_count = 0
    
    try:
        # Query all items for this device
        response = table.query(
            KeyConditionExpression=Key('device_id').eq(device_id),
            ProjectionExpression='device_id, #ts',
            ExpressionAttributeNames={'#ts': 'timestamp'}
        )
        
        items_to_delete = response.get('Items', [])
        
        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('device_id').eq(device_id),
                ProjectionExpression='device_id, #ts',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items_to_delete.extend(response.get('Items', []))
        
        # Delete items in batches of 25 (DynamoDB limit)
        for i in range(0, len(items_to_delete), 25):
            batch = items_to_delete[i:i + 25]
            
            with table.batch_writer() as batch_writer:
                for item in batch:
                    batch_writer.delete_item(
                        Key={'device_id': item['device_id'], 'timestamp': item['timestamp']}
                    )
                    deleted_count += 1
        
        print(f"[_delete_device_data_from_table] Deleted {deleted_count} items from {table_name}")
        return deleted_count
        
    except Exception as e:
        print(f"[_delete_device_data_from_table] ERROR deleting from {table_name}: {str(e)}")
        raise

def _delete_s3_objects_for_device(device_id: str, bucket_name: str, prefix: str) -> int:
    """Delete all S3 objects for a device from a specific bucket."""
    import boto3
    
    s3_client = boto3.client('s3')
    deleted_count = 0
    
    try:
        # List all objects with the device prefix
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=f"{prefix}/")
        
        objects_to_delete = []
        for page in pages:
            if 'Contents' in page:
                objects_to_delete.extend([{'Key': obj['Key']} for obj in page['Contents']])
        
        # Delete objects in batches of 1000 (S3 limit)
        for i in range(0, len(objects_to_delete), 1000):
            batch = objects_to_delete[i:i + 1000]
            
            if batch:
                response = s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': batch, 'Quiet': True}
                )
                deleted_count += len(batch)
                
                # Log any errors
                if 'Errors' in response:
                    for error in response['Errors']:
                        print(f"[_delete_s3_objects_for_device] Error deleting {error['Key']}: {error['Message']}")
        
        print(f"[_delete_s3_objects_for_device] Deleted {deleted_count} objects from s3://{bucket_name}/{prefix}/")
        return deleted_count
        
    except Exception as e:
        print(f"[_delete_s3_objects_for_device] ERROR deleting from s3://{bucket_name}: {str(e)}")
        raise

def delete_device(device_id: str, cascade: bool = True) -> Dict[str, Any]:
    """Delete a device and optionally all associated data (cascade delete).
    
    Args:
        device_id: The device ID to delete
        cascade: If True, delete all associated data from DynamoDB and S3
    
    Returns:
        Dict with deletion results and counts
    """
    if not device_id:
        return {'statusCode': 400, 'body': json.dumps({'error': 'device_id is required'})}
    
    deletion_summary = {
        'device_id': device_id,
        'device_deleted': False,
        'cascade': cascade,
        'deleted_counts': {}
    }
    
    try:
        if cascade:
            # Delete from all device-related tables
            tables_to_clean = [
                (DETECTIONS_TABLE, 'detections'),
                (CLASSIFICATIONS_TABLE, 'classifications'), 
                (VIDEOS_TABLE, 'videos'),
                (ENVIRONMENTAL_READINGS_TABLE, 'environmental_readings')
            ]
            
            for table_name, data_type in tables_to_clean:
                try:
                    count = _delete_device_data_from_table(device_id, table_name)
                    deletion_summary['deleted_counts'][data_type] = count
                except Exception as e:
                    print(f"[delete_device] Failed to delete {data_type}: {str(e)}")
                    deletion_summary['deleted_counts'][data_type] = f"ERROR: {str(e)}"
            
            # Delete S3 objects
            s3_operations = [
                ('scl-sensing-garden-images', 'detection', 'images'),
                ('scl-sensing-garden-images', 'classification', 'images'),
                ('scl-sensing-garden-videos', 'videos', 'videos')
            ]
            
            total_images = 0
            total_videos = 0
            
            for bucket_name, prefix, data_type in s3_operations:
                try:
                    count = _delete_s3_objects_for_device(device_id, bucket_name, f"{prefix}/{device_id}")
                    if data_type == 'images':
                        total_images += count
                    else:
                        total_videos += count
                except Exception as e:
                    print(f"[delete_device] Failed to delete S3 {data_type} from {prefix}: {str(e)}")
            
            deletion_summary['deleted_counts']['s3_images'] = total_images
            deletion_summary['deleted_counts']['s3_videos'] = total_videos
        
        # Finally, delete the device record itself
        device_table = dynamodb.Table(DEVICES_TABLE)
        device_table.delete_item(Key={'device_id': device_id})
        deletion_summary['device_deleted'] = True
        
        result = {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Device {device_id} deleted successfully' + (' with all associated data' if cascade else ''),
                'summary': deletion_summary
            }, cls=DynamoDBEncoder)
        }
        
    except Exception as e:
        print(f"[delete_device] ERROR: {str(e)}")
        result = {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'summary': deletion_summary
            }, cls=DynamoDBEncoder)
        }
    
    return result


def delete_model(model_id: str) -> Dict[str, Any]:
    """Delete a model record from the models table."""
    if not model_id:
        return {'statusCode': 400, 'body': json.dumps({'error': 'model_id is required'})}

    try:
        table = dynamodb.Table(MODELS_TABLE)
        lookup = table.query(
            KeyConditionExpression=Key('id').eq(model_id),
            Limit=1,
            ScanIndexForward=False,
        )
        items = lookup.get('Items', [])
        if not items:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Model {model_id} not found'}, cls=DynamoDBEncoder),
            }

        existing = items[0]
        response = table.delete_item(
            Key={'id': model_id, 'timestamp': existing['timestamp']},
            ReturnValues='ALL_OLD',
        )
        deleted = response.get('Attributes')
        if not deleted:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Model {model_id} not found'}, cls=DynamoDBEncoder),
            }

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Model {model_id} deleted successfully',
                'data': deleted,
            }, cls=DynamoDBEncoder),
        }
    except Exception as e:
        print(f"[delete_model] ERROR: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=DynamoDBEncoder),
        }

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
            'environmental_reading': 'environmental_readings',
            'deployment': 'deployments',
            'deployment_device_connection': 'deployment_device_connections',
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


def _response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'body': json.dumps(payload, cls=DynamoDBEncoder),
    }


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        pass
    for fmt in ('%Y%m%d_%H%M%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(str(value), fmt)
        except Exception:
            continue
    return None


def _timestamp_in_range(timestamp: Optional[str], start_time: Optional[str], end_time: Optional[str]) -> bool:
    if not start_time and not end_time:
        return True
    parsed = _parse_time(timestamp)
    if parsed is None:
        return False
    start_dt = _parse_time(start_time)
    end_dt = _parse_time(end_time)
    if start_dt and parsed < start_dt:
        return False
    if end_dt and parsed > end_dt:
        return False
    return True


def _coerce_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except Exception:
        return None


def _scan_all(table, **kwargs) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    response = table.scan(**kwargs)
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.scan(**kwargs)
        items.extend(response.get('Items', []))
    return items


def _query_all(table, **kwargs) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    response = table.query(**kwargs)
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.query(**kwargs)
        items.extend(response.get('Items', []))
    return items


def _sort_items(items: List[Dict[str, Any]], sort_by: Optional[str], sort_desc: bool) -> List[Dict[str, Any]]:
    if not sort_by:
        return items

    def sort_key(item: Dict[str, Any]) -> Any:
        if sort_by == 'timestamp':
            parsed = _parse_time(item.get('timestamp'))
            return parsed or datetime.min
        return item.get(sort_by)

    return sorted(items, key=sort_key, reverse=sort_desc)


def _parse_offset_token(next_token: Optional[str]) -> int:
    if not next_token:
        return 0
    try:
        data = json.loads(next_token)
        return max(int(data.get('offset', 0)), 0)
    except Exception as exc:
        raise ValueError('Invalid next_token format') from exc


def _build_offset_token(offset: int) -> str:
    return json.dumps({'offset': offset})


def _paginate_items(items: List[Dict[str, Any]], limit: int, next_token: Optional[str]) -> Dict[str, Any]:
    offset = _parse_offset_token(next_token)
    page = items[offset:offset + limit]
    result = {
        'items': page,
        'count': len(page),
    }
    if offset + limit < len(items):
        result['next_token'] = _build_offset_token(offset + limit)
    return result


def device_exists(device_id: str) -> bool:
    table = dynamodb.Table(DEVICES_TABLE)
    response = table.get_item(Key={'device_id': device_id})
    return 'Item' in response


def get_deployment(deployment_id: str) -> Optional[Dict[str, Any]]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    response = table.get_item(Key={'deployment_id': deployment_id})
    return response.get('Item')


def list_deployments(limit: int = 100, next_token: Optional[str] = None,
                     sort_by: Optional[str] = None, sort_desc: bool = False) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    params: Dict[str, Any] = {'Limit': min(limit, 5000) if limit else 100}
    if next_token:
        try:
            params['ExclusiveStartKey'] = json.loads(next_token)
        except json.JSONDecodeError as exc:
            raise ValueError('Invalid next_token format') from exc
    response = table.scan(**params)
    items = _sort_items(response.get('Items', []), sort_by, sort_desc)
    result = {'items': items, 'count': len(items)}
    if 'LastEvaluatedKey' in response:
        result['next_token'] = json.dumps(response['LastEvaluatedKey'])
    return result


def store_deployment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    try:
        table.put_item(
            Item=data,
            ConditionExpression='attribute_not_exists(deployment_id)',
        )
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return _response(409, {'error': f"Deployment {data['deployment_id']} already exists"})
        raise
    return _response(200, {'message': 'Deployment stored successfully', 'deployment': data})


def update_deployment_data(deployment_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    if not get_deployment(deployment_id):
        return _response(404, {'error': f'Deployment {deployment_id} not found'})

    update_parts = []
    expr_attr_values = {}
    expr_attr_names = {}
    for key, value in updates.items():
        expr_attr_names[f'#field_{key}'] = key
        expr_attr_values[f':val_{key}'] = value
        update_parts.append(f'#field_{key} = :val_{key}')

    response = table.update_item(
        Key={'deployment_id': deployment_id},
        UpdateExpression='SET ' + ', '.join(update_parts),
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
        ReturnValues='ALL_NEW',
    )
    return _response(200, {'message': 'Deployment updated successfully', 'deployment': response.get('Attributes', {})})


def list_deployment_devices(deployment_id: str) -> List[Dict[str, Any]]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    items = _query_all(
        table,
        KeyConditionExpression=Key('deployment_id').eq(deployment_id),
    )
    return items


def list_device_ids_for_deployment(deployment_id: str) -> List[str]:
    return [item['device_id'] for item in list_deployment_devices(deployment_id) if 'device_id' in item]


def store_deployment_device_connection_data(data: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    try:
        table.put_item(
            Item=data,
            ConditionExpression='attribute_not_exists(deployment_id) AND attribute_not_exists(device_id)',
        )
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return _response(409, {
                'error': f"Deployment device {data['deployment_id']}/{data['device_id']} already exists"
            })
        raise
    return _response(200, data)


def update_deployment_device_connection(deployment_id: str, device_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    existing = table.get_item(Key={'deployment_id': deployment_id, 'device_id': device_id}).get('Item')
    if not existing:
        return _response(404, {'error': f'Deployment device {deployment_id}/{device_id} not found'})

    expr_attr_names = {}
    expr_attr_values = {}
    update_parts = []
    for key, value in updates.items():
        expr_attr_names[f'#field_{key}'] = key
        expr_attr_values[f':val_{key}'] = value
        update_parts.append(f'#field_{key} = :val_{key}')
    response = table.update_item(
        Key={'deployment_id': deployment_id, 'device_id': device_id},
        UpdateExpression='SET ' + ', '.join(update_parts),
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
        ReturnValues='ALL_NEW',
    )
    return _response(200, response.get('Attributes', {}))


def delete_deployment_device_connection(deployment_id: str, device_id: str) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    response = table.delete_item(
        Key={'deployment_id': deployment_id, 'device_id': device_id},
        ReturnValues='ALL_OLD',
    )
    deleted = response.get('Attributes')
    if not deleted:
        return _response(404, {'error': f'Deployment device {deployment_id}/{device_id} not found'})
    return _response(200, deleted)


def delete_deployment(deployment_id: str) -> Dict[str, Any]:
    deployment = get_deployment(deployment_id)
    if not deployment:
        return _response(404, {'error': f'Deployment {deployment_id} not found'})

    connections_table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    connections = list_deployment_devices(deployment_id)
    with connections_table.batch_writer() as batch_writer:
        for connection in connections:
            batch_writer.delete_item(
                Key={'deployment_id': connection['deployment_id'], 'device_id': connection['device_id']}
            )

    deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
    deployments_table.delete_item(Key={'deployment_id': deployment_id})
    return _response(200, {'deployment': deployment, 'deleted_connections': len(connections)})


def _load_table_items_for_devices(table_name: str, device_ids: Optional[List[str]], start_time: Optional[str],
                                  end_time: Optional[str]) -> List[Dict[str, Any]]:
    table = dynamodb.Table(table_name)
    if device_ids is not None:
        if not device_ids:
            return []
        all_items: List[Dict[str, Any]] = []
        for device_id in device_ids:
            all_items.extend(_query_all(table, KeyConditionExpression=Key('device_id').eq(device_id)))
    else:
        all_items = _scan_all(table)

    if start_time or end_time:
        all_items = [
            item for item in all_items
            if _timestamp_in_range(item.get('timestamp'), start_time, end_time)
        ]
    return all_items


def _classification_confidence(item: Dict[str, Any], taxonomy_level: Optional[str]) -> Optional[float]:
    confidence_field = f'{taxonomy_level}_confidence' if taxonomy_level else 'species_confidence'
    confidence = _coerce_number(item.get(confidence_field))
    if confidence is not None:
        return confidence
    for fallback in ('species_confidence', 'genus_confidence', 'family_confidence'):
        confidence = _coerce_number(item.get(fallback))
        if confidence is not None:
            return confidence
    return None


def _filter_classification_items(items: List[Dict[str, Any]], model_id: Optional[str],
                                 min_confidence: Optional[float], taxonomy_level: Optional[str],
                                 selected_taxa: List[str]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in items:
        if model_id and item.get('model_id') != model_id:
            continue
        if min_confidence is not None:
            confidence = _classification_confidence(item, taxonomy_level)
            if confidence is None or confidence < min_confidence:
                continue
        if taxonomy_level and selected_taxa:
            if item.get(taxonomy_level) not in selected_taxa:
                continue
        filtered.append(item)
    return filtered


def list_classifications(device_ids: Optional[List[str]], model_id: Optional[str], start_time: Optional[str],
                         end_time: Optional[str], min_confidence: Optional[float],
                         taxonomy_level: Optional[str], selected_taxa: List[str], limit: int,
                         next_token: Optional[str], sort_by: Optional[str], sort_desc: bool) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    items = _sort_items(items, sort_by or 'timestamp', sort_desc)
    return _paginate_items(items, min(limit, 5000) if limit else 100, next_token)


def count_classifications(device_ids: Optional[List[str]], model_id: Optional[str], start_time: Optional[str],
                          end_time: Optional[str], min_confidence: Optional[float],
                          taxonomy_level: Optional[str], selected_taxa: List[str]) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    return {'count': len(items)}


def get_classification_taxa_count(device_ids: Optional[List[str]], model_id: Optional[str], start_time: Optional[str],
                                  end_time: Optional[str], min_confidence: Optional[float],
                                  taxonomy_level: str, selected_taxa: List[str], sort_desc: bool) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    counts: Dict[str, int] = {}
    for item in items:
        taxa_value = item.get(taxonomy_level)
        if not taxa_value:
            continue
        counts[taxa_value] = counts.get(taxa_value, 0) + 1
    counted = [{'taxa': taxa, 'count': count} for taxa, count in counts.items()]
    counted = sorted(counted, key=lambda item: item['count'], reverse=sort_desc)
    return {'counts': counted}


def _bucket_timestamps(items: List[Dict[str, Any]], start_time: str, end_time: Optional[str],
                       interval_length: int, interval_unit: str) -> Dict[str, Any]:
    start_dt = _parse_time(start_time)
    if start_dt is None:
        raise ValueError('Invalid start_time')
    interval_delta = timedelta(hours=interval_length) if interval_unit == 'h' else timedelta(days=interval_length)
    end_dt = _parse_time(end_time)
    if end_dt is None:
        parsed_items = [_parse_time(item.get('timestamp')) for item in items if _parse_time(item.get('timestamp'))]
        end_dt = (max(parsed_items) + interval_delta) if parsed_items else (start_dt + interval_delta)
    if end_dt <= start_dt:
        end_dt = start_dt + interval_delta
    bucket_count = max(int((end_dt - start_dt) / interval_delta), 1)
    return {
        'start_dt': start_dt,
        'end_dt': end_dt,
        'interval_delta': interval_delta,
        'bucket_count': bucket_count,
    }


def get_classification_time_series(device_ids: Optional[List[str]], model_id: Optional[str], start_time: str,
                                   end_time: Optional[str], min_confidence: Optional[float],
                                   taxonomy_level: Optional[str], selected_taxa: List[str],
                                   interval_length: int, interval_unit: str) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    bucket_config = _bucket_timestamps(items, start_time, end_time, interval_length, interval_unit)
    counts = [0] * bucket_config['bucket_count']
    for item in items:
        item_time = _parse_time(item.get('timestamp'))
        if not item_time:
            continue
        if item_time < bucket_config['start_dt'] or item_time >= bucket_config['end_dt']:
            continue
        bucket_index = int((item_time - bucket_config['start_dt']) / bucket_config['interval_delta'])
        if 0 <= bucket_index < len(counts):
            counts[bucket_index] += 1
    return {
        'counts': counts,
        'start_time': bucket_config['start_dt'].isoformat(),
        'interval_length': interval_length,
        'interval_unit': interval_unit,
    }


def get_environment_time_series(device_ids: Optional[List[str]], start_time: str, end_time: Optional[str],
                                interval_length: int, interval_unit: str) -> Dict[str, Any]:
    items = _load_table_items_for_devices(ENVIRONMENTAL_READINGS_TABLE, device_ids, start_time, end_time)
    bucket_config = _bucket_timestamps(items, start_time, end_time, interval_length, interval_unit)
    metric_map = {
        'ambient_temperature': 'temperature',
        'ambient_humidity': 'humidity',
        'pm1p0': 'pm1p0',
        'pm2p5': 'pm2p5',
        'pm4p0': 'pm4p0',
        'pm10p0': 'pm10',
        'voc_index': 'voc',
        'nox_index': 'nox',
    }
    bucket_totals = {output_key: [0.0] * bucket_config['bucket_count'] for output_key in metric_map.values()}
    bucket_counts = {output_key: [0] * bucket_config['bucket_count'] for output_key in metric_map.values()}

    for item in items:
        item_time = _parse_time(item.get('timestamp'))
        if not item_time:
            continue
        if item_time < bucket_config['start_dt'] or item_time >= bucket_config['end_dt']:
            continue
        bucket_index = int((item_time - bucket_config['start_dt']) / bucket_config['interval_delta'])
        if not (0 <= bucket_index < bucket_config['bucket_count']):
            continue
        for source_key, output_key in metric_map.items():
            value = _coerce_number(item.get(source_key))
            if value is None:
                continue
            bucket_totals[output_key][bucket_index] += value
            bucket_counts[output_key][bucket_index] += 1

    result = {}
    for output_key in metric_map.values():
        result[output_key] = [
            (bucket_totals[output_key][index] / bucket_counts[output_key][index]) if bucket_counts[output_key][index] else 0
            for index in range(bucket_config['bucket_count'])
        ]

    result.update({
        'start_time': bucket_config['start_dt'].isoformat(),
        'interval_length': interval_length,
        'interval_unit': interval_unit,
    })
    return result


def _load_items_for_query_data(table_type: str, device_id: Optional[str], model_id: Optional[str]) -> List[Dict[str, Any]]:
    table_name = {
        'detection': DETECTIONS_TABLE,
        'classification': CLASSIFICATIONS_TABLE,
        'model': MODELS_TABLE,
        'video': VIDEOS_TABLE,
        'environmental_reading': ENVIRONMENTAL_READINGS_TABLE,
    }[table_type]
    table = dynamodb.Table(table_name)

    if table_type in {'detection', 'classification', 'video', 'environmental_reading'} and device_id:
        return _query_all(table, KeyConditionExpression=Key('device_id').eq(device_id))

    if table_type == 'model' and model_id:
        item = table.get_item(Key={'id': model_id}).get('Item')
        return [item] if item else []

    return _scan_all(table)


def _filter_items_for_query_data(table_type: str, items: List[Dict[str, Any]], device_id: Optional[str],
                                 model_id: Optional[str], start_time: Optional[str],
                                 end_time: Optional[str]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in items:
        if table_type == 'model':
            if device_id and item.get('device_id') != device_id:
                continue
            if model_id and item.get('id') != model_id:
                continue
        elif table_type in {'detection', 'classification', 'video'}:
            if device_id and item.get('device_id') != device_id:
                continue
            if model_id and item.get('model_id') != model_id:
                continue
        elif table_type == 'environmental_reading' and device_id and item.get('device_id') != device_id:
            continue

        if (start_time or end_time) and not _timestamp_in_range(item.get('timestamp'), start_time, end_time):
            continue

        filtered.append(item)
    return filtered

def count_data(table_type: str, device_id: Optional[str] = None, model_id: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
    """Count items in DynamoDB with filtering (efficiently using Select='COUNT')"""
    if table_type not in ['detection', 'classification', 'model', 'video', 'environmental_reading']:
        raise ValueError(f"Invalid table_type: {table_type}")

    items = _load_items_for_query_data(table_type, device_id, model_id)
    items = _filter_items_for_query_data(table_type, items, device_id, model_id, start_time, end_time)
    return {'count': len(items)}

def query_data(table_type: str, device_id: Optional[str] = None, model_id: Optional[str] = None, start_time: Optional[str] = None,
               end_time: Optional[str] = None, limit: int = 100, next_token: Optional[str] = None,
               sort_by: Optional[str] = None, sort_desc: bool = False) -> Dict[str, Any]:
    """Unified query for all DynamoDB tables with filtering and pagination."""
    if table_type not in ['detection', 'classification', 'model', 'video', 'environmental_reading']:
        raise ValueError(f"Invalid table_type: {table_type}")

    items = _load_items_for_query_data(table_type, device_id, model_id)
    items = _filter_items_for_query_data(table_type, items, device_id, model_id, start_time, end_time)
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
    return _paginate_items(items, min(limit, 5000) if limit else 100, next_token)

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
