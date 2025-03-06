import json
import os
import base64
import boto3
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

def _upload_image_to_s3(image_data, device_id, data_type):
    """Upload base64 encoded image to S3
    
    Args:
        image_data (str): Base64 encoded image data
        device_id (str): Device ID for the image
        bucket_name (str): Name of the S3 bucket to upload to
        
    Returns:
        str: S3 URL of the uploaded image
    """
    # Decode base64 image
    image_bytes = base64.b64decode(image_data)
    
    # Generate S3 key with folder structure based on data type
    timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = f"{data_type}/{device_id}/{timestamp}.jpg"
    
    # Upload to S3
    s3.put_object(
        Bucket=IMAGES_BUCKET,
        Key=s3_key,
        Body=image_bytes,
        ContentType='image/jpeg'
    )
    
    # Generate S3 URL
    return f"https://{IMAGES_BUCKET}.s3.amazonaws.com/{s3_key}"

def _parse_request(event):
    """Parse the incoming request from API Gateway or direct invocation
    
    Args:
        event (dict): The Lambda event
        
    Returns:
        dict: The parsed request body
    """
    # Handle both direct invocation and API Gateway proxy integration
    if 'body' in event:
        # API Gateway integration - body is a string that needs to be parsed
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
    else:
        # Direct Lambda invocation - event is the data
        body = event
        
    print(f"Received request with data: {json.dumps({k: '...' if k == 'image' else v for k, v in body.items()})}")
    return body

def detection(event, context):
    """Lambda handler for processing sensor detections
    
    Expected event format:
    {
        "device_id": "string",
        "model_id": "string",
        "timestamp": "string",
        "image": "base64 encoded string"
    }
    """
    try:
        # Parse request body
        body = _parse_request(event)
        
        # Upload image to S3 in the 'detections' folder
        s3_image_link = _upload_image_to_s3(
            body['image'],
            body['device_id'],
            'detections'
        )
        
        # Prepare data for DynamoDB
        dynamo_data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
            's3_image_link': s3_image_link,
            's3_crop_image_link': '' # Required by schema but will be empty for now
        }
        
        # Store data in DynamoDB
        result = store_detection_data(dynamo_data)
        
        # Use the DecimalEncoder for JSON serialization
        if 'body' in result and isinstance(result['body'], str):
            try:
                # Parse the existing JSON string
                body_dict = json.loads(result['body'])
                # Re-serialize with the custom encoder
                result['body'] = json.dumps(body_dict, cls=DecimalEncoder)
            except json.JSONDecodeError:
                pass
            
        return result
        
    except Exception as e:
        print(f"Error processing detection request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }, cls=DecimalEncoder)
        }

def classification(event, context):
    """Lambda handler for processing plant classifications
    
    Expected event format:
    {
        "device_id": "string",
        "model_id": "string",
        "timestamp": "string",
        "image": "base64 encoded string",
        "genus": "string",
        "family": "string",
        "species": "string",
        "confidence": "float"
    }
    """
    try:
        # Parse request body
        body = _parse_request(event)
        
        # Upload image to S3 in the 'classifications' folder
        s3_image_link = _upload_image_to_s3(
            body['image'],
            body['device_id'],
            'classifications'
        )
        
        # Prepare data for DynamoDB
        dynamo_data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
            's3_image_link': s3_image_link,
            'genus': body.get('genus', ''),
            'family': body.get('family', ''),
            'species': body.get('species', ''),
            'confidence': Decimal(str(body.get('confidence', '0.0')))
        }
        
        # Store data in DynamoDB
        result = store_classification_data(dynamo_data)
        
        # Use the DecimalEncoder for JSON serialization
        if 'body' in result and isinstance(result['body'], str):
            try:
                # Parse the existing JSON string
                body_dict = json.loads(result['body'])
                # Re-serialize with the custom encoder
                result['body'] = json.dumps(body_dict, cls=DecimalEncoder)
            except json.JSONDecodeError:
                pass
            
        return result
        
    except Exception as e:
        print(f"Error processing classification request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }, cls=DecimalEncoder)
        }