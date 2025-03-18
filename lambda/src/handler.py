import base64
import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Union

import boto3

from . import dynamodb

# Initialize S3 client
s3 = boto3.client('s3')

# Resource names
IMAGES_BUCKET = "sensing-garden-images"

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
    # Handle both direct invocation and API Gateway proxy integration
    body = event
    if 'body' in event:
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
        
    print(f"Received request with data: {json.dumps({k: '...' if k == 'image' else v for k, v in body.items()})}")
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

def handle_get_detections(event: Dict) -> Dict:
    """Handle GET /detections endpoint"""
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        result = dynamodb.query_data(
            'detection',
            device_id=query_params.get('device_id'),
            model_id=query_params.get('model_id'),
            start_time=query_params.get('start_time'),
            end_time=query_params.get('end_time'),
            limit=int(query_params.get('limit', 100)),
            next_token=query_params.get('next_token')
        )
        
        # Add presigned URLs for images
        for item in result['items']:
            if 'image_key' in item and 'image_bucket' in item:
                item['image_url'] = generate_presigned_url(item['image_key'])
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    except ValueError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)})
        }
    except Exception as e:
        print(f"Error in handle_get_detections: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_post_detection(event: Dict) -> Dict:
    """Handle POST /detections endpoint"""
    try:
        body = _parse_request(event)
        is_valid, error_message = _validate_api_request(body, 'detection_request')
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_message})
            }
        
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
        
        return dynamodb.store_detection_data(data)
    except Exception as e:
        print(f"Error in handle_post_detection: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_get_classifications(event: Dict) -> Dict:
    """Handle GET /classifications endpoint"""
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        result = dynamodb.query_data(
            'classification',
            device_id=query_params.get('device_id'),
            model_id=query_params.get('model_id'),
            start_time=query_params.get('start_time'),
            end_time=query_params.get('end_time'),
            limit=int(query_params.get('limit', 100)),
            next_token=query_params.get('next_token')
        )
        
        # Add presigned URLs for images
        for item in result['items']:
            if 'image_key' in item and 'image_bucket' in item:
                item['image_url'] = generate_presigned_url(item['image_key'])
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    except ValueError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)})
        }
    except Exception as e:
        print(f"Error in handle_get_classifications: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_post_classification(event: Dict) -> Dict:
    """Handle POST /classifications endpoint"""
    try:
        body = _parse_request(event)
        is_valid, error_message = _validate_api_request(body, 'classification_request')
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_message})
            }
        
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
    except Exception as e:
        print(f"Error in handle_post_classification: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_get_models(event: Dict) -> Dict:
    """Handle GET /models endpoint"""
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        result = dynamodb.query_data(
            'model',
            device_id=query_params.get('device_id'),
            model_id=query_params.get('model_id'),
            start_time=query_params.get('start_time'),
            end_time=query_params.get('end_time'),
            limit=int(query_params.get('limit', 100)),
            next_token=query_params.get('next_token')
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    except ValueError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)})
        }
    except Exception as e:
        print(f"Error in handle_get_models: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_post_model(event: Dict) -> Dict:
    """Handle POST /models endpoint"""
    try:
        body = _parse_request(event)
        is_valid, error_message = _validate_api_request(body, 'model_request')
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_message})
            }
        
        # Prepare data for DynamoDB
        data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
            'name': body['name'],
            'description': body['description'],
            'version': body['version']
        }
        
        if 'metadata' in body:
            data['metadata'] = body['metadata']
        
        return dynamodb.store_model_data(data)
    except Exception as e:
        print(f"Error in handle_post_model: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def _process_write_request(event: Dict, data_type: str) -> Dict:
    """Process write requests for detections, classifications, and models"""
    try:
        # Parse request body
        body = _parse_request(event)
        
        # Validate request
        request_type = f"{data_type}_request"
        is_valid, error_message = _validate_api_request(body, request_type)
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f"Invalid request: {error_message}"})
            }
        
        # Generate timestamps
        timestamp_str = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
        iso_timestamp = datetime.utcnow().isoformat()
        
        # Prepare base data
        dynamo_data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', iso_timestamp)
        }
        
        # Handle image upload for detections and classifications
        if data_type in ['detection', 'classification']:
            s3_key = _upload_image_to_s3(body['image'], body['device_id'], data_type, timestamp_str)
            dynamo_data.update({
                'image_key': s3_key,
                'image_bucket': IMAGES_BUCKET
            })
        
        # Add classification-specific fields
        if data_type == 'classification':
            for field in ['family', 'genus', 'species', 'family_confidence', 'genus_confidence', 'species_confidence']:
                if 'confidence' in field:
                    dynamo_data[field] = Decimal(str(body[field]))
                else:
                    dynamo_data[field] = body[field]
        # Add model-specific fields
        elif data_type == 'model':
            for field in ['name', 'description', 'version']:
                dynamo_data[field] = body[field]
            if 'metadata' in body:
                dynamo_data['metadata'] = body['metadata']
        
        # Map data type to table name
        table_mapping = {
            'detection': DETECTIONS_TABLE,
            'classification': CLASSIFICATIONS_TABLE,
            'model': MODELS_TABLE
        }
        
        # Write to DynamoDB
        return _write_to_dynamodb(table_mapping[data_type], dynamo_data)
        
    except Exception as e:
        print(f"Error processing {data_type} write request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def _process_read_request(event: Dict, data_type: str) -> Dict:
    """Process read requests for detections, classifications, and models"""
    try:
        # Get query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        device_id = query_params.get('device_id')
        start_time = query_params.get('start_time')
        end_time = query_params.get('end_time')
        limit = int(query_params.get('limit', 100))
        next_token = query_params.get('next_token')
        
        # Map data type to table name
        table_mapping = {
            'detection': DETECTIONS_TABLE,
            'classification': CLASSIFICATIONS_TABLE,
            'model': MODELS_TABLE
        }
        
        # Query DynamoDB
        return _query_dynamodb(
            table_mapping[data_type],
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            next_token=next_token
        )
        
    except Exception as e:
        print(f"Error processing {data_type} read request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def handler(event: Dict, context) -> Dict:
    """Main Lambda handler for API Gateway requests"""
    try:
        # Get HTTP method and path
        http_method = event.get('httpMethod')
        path = event.get('path', '')
        
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
        
        # Find handler for the endpoint
        handler_func = handlers.get((http_method, path))
        if not handler_func:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'No handler found for {http_method} {path}'
                })
            }
        
        # Call the handler
        result = handler_func(event)
        
        # Add CORS headers
        if 'headers' not in result:
            result['headers'] = {}
        result['headers'].update({
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        })
        
        return result
        
    except Exception as e:
        print(f"Error in main handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }