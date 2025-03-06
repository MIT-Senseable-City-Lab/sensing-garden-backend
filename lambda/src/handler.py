import json
import base64
import boto3
from datetime import datetime
from decimal import Decimal
from dynamodb import store_detection_data, store_classification_data, _load_schema

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

def _upload_image_to_s3(image_data, device_id, data_type):
    """Upload base64 encoded image to S3"""
    # Decode base64 image and upload to S3
    timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = f"{data_type}/{device_id}/{timestamp}.jpg"
    
    s3.put_object(
        Bucket=IMAGES_BUCKET,
        Key=s3_key,
        Body=base64.b64decode(image_data),
        ContentType='image/jpeg'
    )
    
    return f"https://{IMAGES_BUCKET}.s3.amazonaws.com/{s3_key}"

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
    schema = _load_schema()
    api_schema = schema['api'][request_type]
    
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
            elif field_type == 'float' and not isinstance(value, (int, float, str)) or \
                 field_type == 'float' and isinstance(value, str) and not value.replace('.', '', 1).isdigit():
                return False, f"Field {field} should be a number"
    
    return True, ""

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
        
        # Upload image to S3
        s3_image_link = _upload_image_to_s3(body['image'], body['device_id'], data_type)
        
        # Prepare base data for DynamoDB
        dynamo_data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
            'image_link': s3_image_link
        }
        
        # Add additional fields for classification
        if request_type == 'classification_request':
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
        
    except Exception as e:
        print(f"Error processing {request_type}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}, cls=DecimalEncoder)
        }

def detection(event, context):
    """Lambda handler for processing sensor detections"""
    return _process_request(event, context, 'detection_request', 'detections', store_detection_data)

def classification(event, context):
    """Lambda handler for processing plant classifications"""
    return _process_request(event, context, 'classification_request', 'classifications', store_classification_data)