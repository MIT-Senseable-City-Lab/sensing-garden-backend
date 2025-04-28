import base64
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Union, Any, Tuple, Callable

# Custom JSON encoder to handle Decimal serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

import boto3

# Use absolute import instead of relative import for Lambda environment
try:
    # Try importing as a module first (for local development)
    from . import dynamodb
except ImportError:
    # Fallback for Lambda environment
    import dynamodb

# Initialize S3 client
s3 = boto3.client('s3')

# Resource names
IMAGES_BUCKET = "scl-sensing-garden-images"
VIDEOS_BUCKET = "scl-sensing-garden-videos"

# Load the API schema once
def _load_api_schema():
    """Load the API schema for request validation"""
    try:
        # First try to look for schema in the deployed Lambda environment
        schema_path = os.path.join('/opt', 'api-schema.json')
        if os.path.exists(schema_path):
            print(f"Loading API schema from Lambda layer: {schema_path}")
            with open(schema_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Could not load API schema from Lambda layer: {str(e)}")
    
    # Fall back to loading from common directory during local development
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    schema_path = os.path.join(base_dir, 'common', 'api-schema.json')
    print(f"Loading API schema from local path: {schema_path}")
    
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        error_msg = f"Failed to load API schema from {schema_path}: {str(e)}"
        print(error_msg)
        raise ValueError(error_msg)

# Load the schema once
API_SCHEMA = _load_api_schema()

def _upload_image_to_s3(image_data, device_id, data_type, timestamp=None):
    """Upload base64 encoded image to S3"""
    # Decode base64 image and upload to S3
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = f"{data_type}/{device_id}/{timestamp}.jpg"
    
    s3.put_object(
        Bucket=IMAGES_BUCKET,
        Key=s3_key,
        Body=base64.b64decode(image_data),
        ContentType='image/jpeg'
    )
    
    # Store the S3 key rather than a direct URL
    # We'll generate presigned URLs when needed
    return s3_key

def _upload_video_to_s3(video_data, device_id, timestamp=None, content_type='video/mp4'):
    """Upload base64 encoded video to S3"""
    # Decode base64 video and upload to S3
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
    
    # Determine file extension based on content type
    extension = 'mp4'  # Default
    if content_type:
        if 'mp4' in content_type:
            extension = 'mp4'
        elif 'webm' in content_type:
            extension = 'webm'
        elif 'mov' in content_type:
            extension = 'mov'
        elif 'avi' in content_type:
            extension = 'avi'
    
    s3_key = f"videos/{device_id}/{timestamp}.{extension}"
    
    s3.put_object(
        Bucket=VIDEOS_BUCKET,
        Key=s3_key,
        Body=base64.b64decode(video_data),
        ContentType=content_type
    )
    
    # Store the S3 key rather than a direct URL
    # We'll generate presigned URLs when needed
    return s3_key













def _parse_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the incoming request from API Gateway or direct invocation"""
    # Print the event structure for debugging
    print(f"Event structure: {json.dumps({k: type(v).__name__ for k, v in event.items()}, cls=dynamodb.DynamoDBEncoder)}")
    
    # Handle both direct invocation and API Gateway proxy integration
    if 'body' not in event:
        # Direct invocation where the entire event is the body
        print("Direct invocation detected, using event as body")
        body = event
    else:
        # API Gateway integration
        # Check if the body is already a dict (as sometimes happens with HTTP API v2)
        if isinstance(event.get('body'), dict):
            body = event['body']
        else:
            # If body is string, try to parse as JSON
            try:
                body = json.loads(event['body']) if event.get('body') else {}
            except (TypeError, json.JSONDecodeError) as e:
                print(f"Error parsing request body: {str(e)}")
                body = {}
                if event.get('body'):
                    print(f"Raw body: {event['body'][:100]}...")
    
    # Safely handle printing the body (without large base64 images)
    try:
        body_for_log = {k: '...' if k == 'image' else v for k, v in body.items()}
        print(f"Processed request body: {json.dumps(body_for_log, cls=dynamodb.DynamoDBEncoder)}") 
    except Exception as e:
        print(f"Error logging request body: {str(e)}")
    
    return body

def _validate_api_request(body: Dict[str, Any], request_type: str) -> (bool, str):
    """Validate API request against schema"""
    # Map from request_type to actual schema name in the OpenAPI spec
    schema_type_map = {
        'detection_request': 'DetectionData',
        'classification_request': 'ClassificationData',
        'model_request': 'ModelData',
        'video_request': 'VideoData',
        'video_registration_request': 'VideoRegistrationRequest'
    }
    
    # Get schema from the OpenAPI spec
    schema_name = schema_type_map.get(request_type)
    if not schema_name or schema_name not in API_SCHEMA['components']['schemas']:
        print(f"Schema not found for request type: {request_type}")
        print(f"Available schemas: {list(API_SCHEMA['components']['schemas'].keys())}")
        return False, f"Invalid request type: {request_type}"
    
    api_schema = API_SCHEMA['components']['schemas'][schema_name]
    
    # Print schema information for debugging
    print(f"Using schema: {schema_name}")
    print(f"Schema required fields: {api_schema.get('required', [])}")
    print(f"Schema properties: {list(api_schema.get('properties', {}).keys())}")
    
    # Check required fields
    required_fields = api_schema.get('required', [])
    missing_fields = [field for field in required_fields if field not in body]
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    # Check field types
    for field, value in body.items():
        if field in api_schema.get('properties', {}):
            field_type = api_schema['properties'][field].get('type')
            if field_type == 'string' and not isinstance(value, str):
                return False, f"Field {field} should be a string"
            elif field_type == 'number' and not isinstance(value, (int, float, str)) or \
                 field_type == 'number' and isinstance(value, str) and not value.replace('.', '', 1).isdigit():
                return False, f"Field {field} should be a number"
    
    return True, ""

def generate_presigned_url(s3_key: str, bucket: Optional[str] = None, expiration: int = 3600) -> Optional[str]:
    """Generate a presigned URL for accessing an S3 object"""
    try:
        # Default to images bucket if no bucket is specified
        if bucket is None:
            bucket = IMAGES_BUCKET
            
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket,
                'Key': s3_key
            },
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return None

def _add_presigned_urls(result: Dict[str, Any]) -> Dict[str, Any]:
    """Add presigned URLs to image and video items"""
    for item in result['items']:
        # Handle image URLs
        if 'image_key' in item and 'image_bucket' in item:
            item['image_url'] = generate_presigned_url(item['image_key'], item['image_bucket'])
        # Handle video URLs
        if 'video_key' in item and 'video_bucket' in item:
            item['video_url'] = generate_presigned_url(item['video_key'], item['video_bucket'])
    return result

def handle_count_detections(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /detections/count endpoint"""
    try:
        params = event.get('queryStringParameters', {}) or {}
        device_id = params.get('device_id')
        model_id = params.get('model_id')
        start_time = params.get('start_time')
        end_time = params.get('end_time')
        result = dynamodb.count_data('detection', device_id, model_id, start_time, end_time)
        return {
            'statusCode': 200,
            'body': json.dumps(result, cls=dynamodb.DynamoDBEncoder)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

def handle_get_detections(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /detections endpoint"""
    return _common_get_handler(event, 'detection', _add_presigned_urls)

def _store_detection(body: Dict[str, Any]) -> Dict[str, Any]:
    """Process and store detection data"""
    # Upload image to S3
    timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = _upload_image_to_s3(body['image'], body['device_id'], 'detection', timestamp_str)
    
    # Prepare data for DynamoDB
    data = {
        'device_id': body['device_id'],
        'model_id': body['model_id'],
        'timestamp': body.get('timestamp', datetime.now(timezone.utc).isoformat()),
        'image_key': s3_key,
        'image_bucket': IMAGES_BUCKET
    }
    
    # Include bounding_box if present
    if 'bounding_box' in body:
        data['bounding_box'] = body['bounding_box']
    
    return dynamodb.store_detection_data(data)

def handle_post_detection(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /detections endpoint"""
    return _common_post_handler(event, 'detection', _store_detection)

def handle_count_classifications(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /classifications/count endpoint"""
    try:
        params = event.get('queryStringParameters', {}) or {}
        device_id = params.get('device_id')
        model_id = params.get('model_id')
        start_time = params.get('start_time')
        end_time = params.get('end_time')
        result = dynamodb.count_data('classification', device_id, model_id, start_time, end_time)
        return {
            'statusCode': 200,
            'body': json.dumps(result, cls=dynamodb.DynamoDBEncoder)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

def handle_get_classifications(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /classifications endpoint"""
    return _common_get_handler(event, 'classification', _add_presigned_urls)

def _store_classification(body: Dict[str, Any]) -> Dict[str, Any]:
    """Process and store classification data"""
    # Upload image to S3
    timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = _upload_image_to_s3(body['image'], body['device_id'], 'classification', timestamp_str)
    
    # Prepare data for DynamoDB
    data = {
        'device_id': body['device_id'],
        'model_id': body['model_id'],
        'timestamp': body.get('timestamp', datetime.now(timezone.utc).isoformat()),
        'image_key': s3_key,
        'image_bucket': IMAGES_BUCKET,
        'family': body['family'],
        'genus': body['genus'],
        'species': body['species'],
        'family_confidence': Decimal(str(body['family_confidence'])),
        'genus_confidence': Decimal(str(body['genus_confidence'])),
        'species_confidence': Decimal(str(body['species_confidence']))
    }
    if 'bounding_box' in body:
        # Convert all bounding_box values to Decimal to avoid float issues with DynamoDB
        box = body['bounding_box']
        if isinstance(box, list):
            data['bounding_box'] = [Decimal(str(x)) for x in box]
        else:
            data['bounding_box'] = box
    
    return dynamodb.store_classification_data(data)

def handle_post_classification(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /classifications endpoint"""
    return _common_post_handler(event, 'classification', _store_classification)

def handle_count_models(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /models/count endpoint"""
    try:
        # Parse query params
        params = event.get('queryStringParameters', {}) or {}
        device_id = params.get('device_id')
        model_id = params.get('model_id')
        start_time = params.get('start_time')
        end_time = params.get('end_time')
        result = dynamodb.count_data('model', device_id, model_id, start_time, end_time)
        return {
            'statusCode': 200,
            'body': json.dumps(result, cls=dynamodb.DynamoDBEncoder)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

def handle_get_models(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /models endpoint"""
    return _common_get_handler(event, 'model')

def handle_get_devices(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /devices endpoint with filtering, pagination, and sorting."""
    params = event.get('queryStringParameters', {}) or {}
    device_id = params.get('device_id')
    created = params.get('created')
    limit = int(params.get('limit', 100))
    next_token = params.get('next_token')
    sort_by = params.get('sort_by')
    sort_desc = params.get('sort_desc', 'false').lower() == 'true'
    result = dynamodb.get_devices(device_id, created, limit, next_token, sort_by, sort_desc)
    return {
        'statusCode': 200,
        'body': json.dumps(result, cls=dynamodb.DynamoDBEncoder)
    }

def handle_post_device(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /devices endpoint."""
    try:
        body = event.get('body')
        if body is None:
            raise ValueError("Request body is required")
        if isinstance(body, str):
            body = json.loads(body)
        device_id = body.get('device_id')
        created = body.get('created')
        if not device_id:
            raise ValueError("device_id is required in body")
        return dynamodb.add_device(device_id, created)
    except Exception as e:
        print(f"[handle_post_device] ERROR: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

def handle_delete_device(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle DELETE /devices endpoint."""
    import traceback
    try:
        body = event.get('body')
        print(f"[handle_delete_device] Raw body: {body}")
        if body is None:
            raise ValueError("Request body is required")
        if isinstance(body, str):
            try:
                body_json = json.loads(body)
            except Exception as decode_err:
                print(f"[handle_delete_device] Could not decode body: {decode_err}")
                raise ValueError(f"Could not decode body: {decode_err}")
        else:
            body_json = body
        device_id = body_json.get('device_id')
        if not device_id:
            raise ValueError("device_id is required in body")
        resp = dynamodb.delete_device(device_id)
        print(f"[handle_delete_device] DynamoDB response: {resp}")
        return resp
    except Exception as e:
        trace = traceback.format_exc()
        print(f"[handle_delete_device] ERROR: {str(e)}\n{trace}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e), 'trace': trace, 'event': str(event)}, cls=dynamodb.DynamoDBEncoder)
        }

def _store_model(body: Dict[str, Any]) -> Dict[str, Any]:
    """Process and store model data"""
    # ... (rest of the code remains the same)
    # Prepare data for DynamoDB
    data = {
        'id': body['model_id'],  # Use model_id as the primary key (id)
        'timestamp': body.get('timestamp', datetime.now(timezone.utc).isoformat()),
        'name': body['name'],
        'description': body['description'],
        'version': body['version']
    }
    
    if 'metadata' in body:
        data['metadata'] = body['metadata']
    
    return dynamodb.store_model_data(data)

def handle_post_model(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /models endpoint"""
    return _common_post_handler(event, 'model', _store_model)

def handle_count_videos(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /videos/count endpoint"""
    try:
        params = event.get('queryStringParameters', {}) or {}
        device_id = params.get('device_id')
        start_time = params.get('start_time')
        end_time = params.get('end_time')
        result = dynamodb.count_data('video', device_id, None, start_time, end_time)
        return {
            'statusCode': 200,
            'body': json.dumps(result, cls=dynamodb.DynamoDBEncoder)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

def handle_get_videos(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle GET /videos endpoint"""
    return _common_get_handler(event, 'video', _add_presigned_urls)

def _store_video(body: Dict[str, Any]) -> Dict[str, Any]:
    """Process and store video data"""
    # Get or generate timestamp
    timestamp = body.get('timestamp')
    if timestamp:
        # Use the provided timestamp for the S3 key
        timestamp_str = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d-%H-%M-%S')
    else:
        # Generate a new timestamp if not provided
        timestamp = datetime.now(timezone.utc).isoformat()
        timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
    
    # Upload video to S3
    s3_key = _upload_video_to_s3(body['video'], body['device_id'], timestamp_str)
    
    # Prepare data for DynamoDB
    data = {
        'device_id': body['device_id'],
        'timestamp': timestamp,
        'video_key': s3_key,
        'video_bucket': VIDEOS_BUCKET,
        'type': 'video'  # Set the type field required by the schema
    }
    
    # Include metadata if present
    if 'metadata' in body:
        data['metadata'] = body['metadata']
    
    return dynamodb.store_video_data(data)

def handle_post_video(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle POST /videos endpoint"""
    return _common_post_handler(event, 'video', _store_video)





def handle_post_video_register(event: Dict) -> Dict:
    """Handle POST /videos/register endpoint"""
    try:
        # Parse the request body
        body = _parse_request(event)
        
        # Validate the request against the schema
        is_valid, validation_error = _validate_api_request(body, 'video_registration_request')
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f"Invalid request: {validation_error}"
                }, cls=dynamodb.DynamoDBEncoder)
            }
        
        # Get or generate timestamp
        timestamp = body.get('timestamp')
        if not timestamp:
            # Generate a new timestamp if not provided
            timestamp = datetime.now(timezone.utc).isoformat()
        
        # Ensure device is present in devices table
        device_id = body.get('device_id')
        if device_id:
            try:
                dynamodb.store_device_if_not_exists(device_id)
            except Exception as e:
                print(f"Warning: Failed to store device_id {device_id} in devices table: {str(e)}")

        # Prepare data for DynamoDB
        data = {
            'device_id': body['device_id'],
            'timestamp': timestamp,
            'video_key': body['video_key'],
            'video_bucket': VIDEOS_BUCKET,
            'type': 'video'  # Set the type field required by the schema
        }
        
        # Include metadata if present
        if 'metadata' in body:
            data['metadata'] = body['metadata']
        
        # Store video metadata in DynamoDB
        result = dynamodb.store_video_data(data)
        
        # Generate a presigned URL for the video
        video_url = generate_presigned_url(body['video_key'], VIDEOS_BUCKET)
        result['video_url'] = video_url
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Video data stored successfully',
                'data': result
            }, cls=dynamodb.DynamoDBEncoder)
        }
    except Exception as e:
        print(f"Error in handle_post_video_register: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }, cls=dynamodb.DynamoDBEncoder)
        }

def _common_post_handler(event: Dict[str, Any], data_type: str, store_function: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """Common handler for all POST endpoints"""
    try:
        # Parse request body
        body = _parse_request(event)

        # Save device_id in devices table if present
        device_id = body.get('device_id')
        if device_id:
            try:
                dynamodb.store_device_if_not_exists(device_id)
            except Exception as e:
                print(f"Warning: Failed to store device_id {device_id} in devices table: {str(e)}")
        
        # Validate request based on data type
        request_type = f"{data_type}_request"
        is_valid, error_message = _validate_api_request(body, request_type)
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_message}, cls=dynamodb.DynamoDBEncoder)
            }
        
        # Call the appropriate store function with the parsed body
        return store_function(body)
        
    except Exception as e:
        print(f"Error in {data_type} POST handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

def _make_offset_naive(ts):
    from dateutil.parser import isoparse
    from datetime import timezone
    try:
        dt = isoparse(ts)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.isoformat()
    except Exception:
        return ts

def _clean_timestamps(items):
    for item in items:
        if 'timestamp' in item:
            item['timestamp'] = _make_offset_naive(item['timestamp'])
    return items

def _common_get_handler(event: Dict[str, Any], data_type: str, process_results: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Common handler for all GET endpoints"""
    try:
        # Get query parameters with defaults, handling HTTP API v2 format
        query_params = {}
        if 'queryStringParameters' in event:
            query_params = event.get('queryStringParameters', {}) or {}
        print(f"Query parameters: {query_params}")
        result = dynamodb.query_data(
            data_type,
            device_id=query_params.get('device_id'),
            model_id=query_params.get('model_id'),
            start_time=query_params.get('start_time'),
            end_time=query_params.get('end_time'),
            limit=int(query_params.get('limit', 100)) if query_params.get('limit') else 100,
            next_token=query_params.get('next_token'),
            sort_by=query_params.get('sort_by'),
            sort_desc=query_params.get('sort_desc', 'false').lower() == 'true'
        )
        # Clean timestamps to be offset-naive
        if 'items' in result:
            result['items'] = _clean_timestamps(result['items'])
        if process_results:
            result = process_results(result)
        return {
            'statusCode': 200,
            'body': json.dumps(result, cls=dynamodb.DynamoDBEncoder)
        }
    except ValueError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }
    except Exception as e:
        print(f"Error in {data_type} GET handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=dynamodb.DynamoDBEncoder)
        }

from typing import Dict, Any, Optional, Callable

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for API Gateway requests
    
    This handler supports the API Gateway HTTP API (v2) format with PayloadFormatVersion 2.0
    """
    try:
        # Print detailed event structure for debugging
        print(f"Received event keys: {list(event.keys())}")
        for key in event.keys():
            if isinstance(event[key], dict):
                print(f"Event[{key}] sub-keys: {list(event[key].keys())}")
                if key == 'requestContext' and 'http' in event[key]:
                    print(f"HTTP method: {event[key]['http'].get('method')}, Path: {event[key]['http'].get('path')}")
        
        # Determine HTTP method and path
        http_method = event.get('requestContext', {}).get('http', {}).get('method', '')
        path = event.get('requestContext', {}).get('http', {}).get('path', '')
        
        print(f"Dispatching to handler for {http_method} {path}")
        
        # Routing logic
        if http_method == 'GET' and path == '/devices':
            return handle_get_devices(event)
        elif http_method == 'POST' and path == '/devices':
            return handle_post_device(event)
        elif http_method == 'DELETE' and path == '/devices':
            return handle_delete_device(event)
        elif http_method == 'GET' and path == '/detections':
            return handle_get_detections(event)
        elif http_method == 'GET' and path == '/classifications':
            return handle_get_classifications(event)
        elif http_method == 'GET' and path == '/models':
            return handle_get_models(event)
        elif http_method == 'GET' and path == '/videos':
            return handle_get_videos(event)
        elif http_method == 'POST' and path == '/detections':
            return handle_post_detection(event)
        elif http_method == 'POST' and path == '/classifications':
            return handle_post_classification(event)
        elif http_method == 'POST' and path == '/models':
            return handle_post_model(event)
        elif http_method == 'POST' and path == '/videos':
            return handle_post_video(event)
        elif http_method == 'POST' and path == '/videos/register':
            return handle_post_video_register(event)
        elif http_method == 'GET' and path == '/detections/count':
            return handle_count_detections(event)
        elif http_method == 'GET' and path == '/classifications/count':
            return handle_count_classifications(event)
        elif http_method == 'GET' and path == '/models/count':
            return handle_count_models(event)
        elif http_method == 'GET' and path == '/videos/count':
            return handle_count_videos(event)
        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'No handler for {http_method} {path}'}, cls=dynamodb.DynamoDBEncoder)
            }
        
        return result
        
    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        print(f"Error in main handler: {str(e)}")
        print(f"Traceback: {trace}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'trace': trace
            }, cls=dynamodb.DynamoDBEncoder),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }