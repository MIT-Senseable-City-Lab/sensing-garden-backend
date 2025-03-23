import base64
import json
import os
from datetime import datetime
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
        timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
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

def _parse_request(event):
    """Parse the incoming request from API Gateway or direct invocation"""
    # Print the event structure for debugging
    print(f"Event structure: {json.dumps({k: type(v).__name__ for k, v in event.items()}, cls=DecimalEncoder)}")
    
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
        print(f"Processed request body: {json.dumps(body_for_log, cls=DecimalEncoder)}") 
    except Exception as e:
        print(f"Error logging request body: {str(e)}")
    
    return body

def _validate_api_request(body, request_type):
    """Validate API request against schema"""
    # Map from request_type to actual schema name in the OpenAPI spec
    schema_type_map = {
        'detection_request': 'DetectionData',
        'classification_request': 'ClassificationData',
        'model_request': 'ModelData'
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

def generate_presigned_url(s3_key, expiration=3600):
    """Generate a presigned URL for accessing an S3 object"""
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': IMAGES_BUCKET,
                'Key': s3_key
            },
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return None

def _add_presigned_urls(result: Dict) -> Dict:
    """Add presigned URLs to image items"""
    for item in result['items']:
        if 'image_key' in item and 'image_bucket' in item:
            item['image_url'] = generate_presigned_url(item['image_key'])
    return result

def handle_get_detections(event: Dict) -> Dict:
    """Handle GET /detections endpoint"""
    return _common_get_handler(event, 'detection', _add_presigned_urls)

def _store_detection(body: Dict) -> Dict:
    """Process and store detection data"""
    # Upload image to S3
    timestamp_str = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = _upload_image_to_s3(body['image'], body['device_id'], 'detection', timestamp_str)
    
    # Prepare data for DynamoDB
    data = {
        'device_id': body['device_id'],
        'model_id': body['model_id'],
        'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
        'image_key': s3_key,
        'image_bucket': IMAGES_BUCKET
    }
    
    # Include bounding_box if present
    if 'bounding_box' in body:
        data['bounding_box'] = body['bounding_box']
    
    return dynamodb.store_detection_data(data)

def handle_post_detection(event: Dict) -> Dict:
    """Handle POST /detections endpoint"""
    return _common_post_handler(event, 'detection', _store_detection)

def handle_get_classifications(event: Dict) -> Dict:
    """Handle GET /classifications endpoint"""
    return _common_get_handler(event, 'classification', _add_presigned_urls)

def _store_classification(body: Dict) -> Dict:
    """Process and store classification data"""
    # Upload image to S3
    timestamp_str = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = _upload_image_to_s3(body['image'], body['device_id'], 'classification', timestamp_str)
    
    # Prepare data for DynamoDB
    data = {
        'device_id': body['device_id'],
        'model_id': body['model_id'],
        'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
        'image_key': s3_key,
        'image_bucket': IMAGES_BUCKET,
        'family': body['family'],
        'genus': body['genus'],
        'species': body['species'],
        'family_confidence': Decimal(str(body['family_confidence'])),
        'genus_confidence': Decimal(str(body['genus_confidence'])),
        'species_confidence': Decimal(str(body['species_confidence']))
    }
    
    return dynamodb.store_classification_data(data)

def handle_post_classification(event: Dict) -> Dict:
    """Handle POST /classifications endpoint"""
    return _common_post_handler(event, 'classification', _store_classification)

def handle_get_models(event: Dict) -> Dict:
    """Handle GET /models endpoint"""
    return _common_get_handler(event, 'model')

def _store_model(body: Dict) -> Dict:
    """Process and store model data"""
    # Prepare data for DynamoDB
    data = {
        'id': body['model_id'],  # Use model_id as the primary key (id)
        'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
        'name': body['name'],
        'description': body['description'],
        'version': body['version']
    }
    
    if 'metadata' in body:
        data['metadata'] = body['metadata']
    
    return dynamodb.store_model_data(data)

def handle_post_model(event: Dict) -> Dict:
    """Handle POST /models endpoint"""
    return _common_post_handler(event, 'model', _store_model)

def _common_post_handler(event: Dict, data_type: str, store_function: Callable[[Dict], Dict]) -> Dict:
    """Common handler for all POST endpoints"""
    try:
        # Parse request body
        body = _parse_request(event)
        
        # Validate request based on data type
        request_type = f"{data_type}_request"
        is_valid, error_message = _validate_api_request(body, request_type)
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_message}, cls=DecimalEncoder)
            }
        
        # Call the appropriate store function with the parsed body
        return store_function(body)
        
    except Exception as e:
        print(f"Error in {data_type} POST handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=DecimalEncoder)
        }

def _common_get_handler(event: Dict, data_type: str, process_results: Optional[Callable[[Dict], Dict]] = None) -> Dict:
    """Common handler for all GET endpoints"""
    try:
        # Get query parameters with defaults, handling HTTP API v2 format
        query_params = {}
        
        # Try to get query parameters from HTTP API v2 format
        if 'queryStringParameters' in event:
            query_params = event.get('queryStringParameters', {}) or {}
        
        print(f"Query parameters: {query_params}")
        
        # Query data using the dynamodb module
        # Convert sort_desc from string to boolean if provided
        sort_desc = query_params.get('sort_desc', 'false').lower() == 'true'
        
        result = dynamodb.query_data(
            data_type,
            device_id=query_params.get('device_id'),
            model_id=query_params.get('model_id'),
            start_time=query_params.get('start_time'),
            end_time=query_params.get('end_time'),
            limit=int(query_params.get('limit', 100)) if query_params.get('limit') else 100,
            next_token=query_params.get('next_token'),
            sort_by=query_params.get('sort_by'),
            sort_desc=sort_desc
        )
        
        # Apply custom processing to results if provided
        if process_results:
            result = process_results(result)
            
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps(result, cls=DecimalEncoder)
        }
        
    except ValueError as e:
        # Handle validation errors
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)}, cls=DecimalEncoder)
        }
    except Exception as e:
        # Handle all other errors
        print(f"Error in {data_type} GET handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=DecimalEncoder)
        }

def handler(event: Dict, context) -> Dict:
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
                    print(f"HTTP context: {json.dumps(event[key]['http'], cls=DecimalEncoder)}")
            else:
                if key != 'body':  # Don't print body which might be large
                    print(f"Event[{key}] = {event[key]}")
                else:
                    print(f"Event has body of type {type(event['body']).__name__}")
                    if isinstance(event['body'], str):
                        print(f"Body starts with: {event['body'][:30]}...")
        
        # HTTP API v2 stores method and path differently
        http_method = event.get('requestContext', {}).get('http', {}).get('method')
        path = event.get('requestContext', {}).get('http', {}).get('path', '')
        
        # If the HTTP API structure isn't found, fall back to v1 format
        if not http_method or not path:
            http_method = event.get('httpMethod')
            path = event.get('path', '')
            print(f"Using fallback method detection: {http_method} {path}")
        else:
            print(f"Using HTTP API v2 method detection: {http_method} {path}")
            
        # Special handling for HTTP API v2 POST requests
        if http_method == 'POST' and 'body' in event:
            print(f"API Gateway is sending POST body of type: {type(event['body']).__name__}")
            if isinstance(event['body'], str):
                # Try to parse it to see if it's properly formatted
                try:
                    test_parse = json.loads(event['body'])
                    print(f"Body parsed successfully as JSON with keys: {list(test_parse.keys())}")
                except json.JSONDecodeError as e:
                    print(f"Body is not valid JSON: {str(e)}")
                    print(f"Body content (first 100 chars): {event['body'][:100]}")
        
        # Define endpoint handlers using only plural endpoints for consistency
        handlers = {
            # Read endpoints (GET)
            ('GET', '/models'): handle_get_models,
            ('GET', '/detections'): handle_get_detections,
            ('GET', '/classifications'): handle_get_classifications,
            # Write endpoints (POST)
            ('POST', '/models'): handle_post_model,
            ('POST', '/detections'): handle_post_detection,
            ('POST', '/classifications'): handle_post_classification,
        }
        
        print(f"Processing {http_method} {path} request")
        
        # Find handler for the endpoint
        handler_func = handlers.get((http_method, path))
        if not handler_func:
            print(f"No handler found for {http_method} {path}")
            print(f"Available handlers: {list(handlers.keys())}")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'No handler found for {http_method} {path}'
                }, cls=DecimalEncoder)
            }
        
        print(f"Found handler {handler_func.__name__} for {http_method} {path}")
        
        # Call the handler
        result = handler_func(event)
        print(f"Handler result: {json.dumps(result, cls=DecimalEncoder)}")
        
        # Add CORS headers
        if 'headers' not in result:
            result['headers'] = {}
        result['headers'].update({
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        })
        
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
            }, cls=DecimalEncoder),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }