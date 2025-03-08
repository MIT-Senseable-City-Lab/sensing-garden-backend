import json
import base64
import boto3
import os
from datetime import datetime
from decimal import Decimal
from dynamodb import store_detection_data, store_classification_data

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize S3 client
s3 = boto3.client('s3')

# S3 bucket name for all image data
IMAGES_BUCKET = "sensing-garden-images"

# Load the schema once
try:
    # In Lambda environment, we expect the schema to be in /opt/schema/api-schema.json
    # or in the local directory structure
    if os.path.exists('/opt/schema/api-schema.json'):
        API_SCHEMA_PATH = '/opt/schema/api-schema.json'
        print(f"Loading schema from Lambda layer: {API_SCHEMA_PATH}")
    else:
        # Fallback to local path calculation for testing
        API_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'common', 'api-schema.json')
        print(f"Loading schema from local path: {API_SCHEMA_PATH}")
    
    with open(API_SCHEMA_PATH, 'r') as f:
        API_SCHEMA = json.load(f)
    print(f"API Schema loaded successfully with keys: {list(API_SCHEMA.keys())}")
except Exception as e:
    print(f"Error loading API schema: {str(e)}")
    # Provide default minimal schema for error recovery
    API_SCHEMA = {
        "components": {
            "schemas": {
                "DetectionData": {
                    "required": ["device_id", "model_id", "image"],
                    "properties": {
                        "device_id": {"type": "string"},
                        "model_id": {"type": "string"},
                        "image": {"type": "string"}
                    }
                },
                "ClassificationData": {
                    "required": ["device_id", "model_id", "image"],
                    "properties": {
                        "device_id": {"type": "string"},
                        "model_id": {"type": "string"},
                        "image": {"type": "string"},
                        "family": {"type": "string"},
                        "genus": {"type": "string"},
                        "species": {"type": "string"},
                        "family_confidence": {"type": "number"},
                        "genus_confidence": {"type": "number"},
                        "species_confidence": {"type": "number"}
                    }
                }
            }
        }
    }

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
    api_schema = API_SCHEMA['components']['schemas'][request_type]
    
    # Check required fields
    missing_fields = [field for field in api_schema['required'] if field not in body]
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    # Check field types
    for field, value in body.items():
        if field in api_schema['properties']:
            field_type = api_schema['properties'][field]['type']
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

def _process_request(event, context, request_type, data_type, store_function):
    """Generic request processor for both detection and classification"""
    try:
        # Parse and validate request
        body = _parse_request(event)
        is_valid, error_message = _validate_api_request(body, request_type)
        if not is_valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f"Invalid request: {error_message}"})
            }
        
        # Generate consistent timestamp for both S3 and DynamoDB
        timestamp_str = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
        iso_timestamp = datetime.utcnow().isoformat()
        
        # Upload image to S3 and get the S3 key using the same timestamp
        s3_key = _upload_image_to_s3(body['image'], body['device_id'], data_type, timestamp_str)
        
        # Prepare base data for DynamoDB using the timestamp we already generated
        dynamo_data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', iso_timestamp),
            'image_key': s3_key,  # Store the S3 key instead of a direct URL
            'image_bucket': IMAGES_BUCKET  # Store the bucket name for future reference
        }
        
        # Add additional fields for classification
        if request_type == 'ClassificationData':
            for field in ['family', 'genus', 'species', 'family_confidence', 'genus_confidence', 'species_confidence']:
                if field in body:
                    # Convert confidence values to Decimal for DynamoDB
                    if 'confidence' in field:
                        dynamo_data[field] = Decimal(str(body[field]))
                    else:
                        dynamo_data[field] = body[field]
        
        # Store data and return result
        result = store_function(dynamo_data)
        
        # Ensure proper JSON serialization
        if 'body' in result and isinstance(result['body'], str):
            try:
                body_dict = json.loads(result['body'])
                result['body'] = json.dumps(body_dict, cls=DecimalEncoder)
            except json.JSONDecodeError:
                pass
                
        return result
        
    except KeyError as e:
        error_message = f"Missing key in request: {str(e)}"
        print(error_message)
        return {
            'statusCode': 400,
            'body': json.dumps({'error': error_message})
        }
    except ValueError as e:
        error_message = f"Value error: {str(e)}"
        print(error_message)
        return {
            'statusCode': 400,
            'body': json.dumps({'error': error_message})
        }
    except Exception as e:
        error_message = f"Error processing {request_type}: {str(e)}"
        print(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_message}, cls=DecimalEncoder)
        }

def detection(event, context):
    """Lambda handler for processing sensor detections"""
    return _process_request(event, context, 'DetectionData', 'detections', store_detection_data)

def classification(event, context):
    """Lambda handler for processing plant classifications"""
    return _process_request(event, context, 'ClassificationData', 'classifications', store_classification_data)