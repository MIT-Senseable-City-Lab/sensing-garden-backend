import json
import os
import base64
import boto3
from datetime import datetime
from dynamodb import store_sensor_data

# Initialize S3 client
s3 = boto3.client('s3')
BUCKET_NAME = os.environ['S3_BUCKET_NAME']

def upload_image_to_s3(image_data, device_id):
    """Upload base64 encoded image to S3
    
    Args:
        image_data (str): Base64 encoded image data
        device_id (str): Device ID for the image
        
    Returns:
        str: S3 URL of the uploaded image
    """
    # Decode base64 image
    image_bytes = base64.b64decode(image_data)
    
    # Generate S3 key
    timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
    s3_key = f"{device_id}/{timestamp}.jpg"
    
    # Upload to S3
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=image_bytes,
        ContentType='image/jpeg'
    )
    
    # Generate S3 URL
    return f"https://{BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

def handler(event, context):
    """Lambda handler for processing sensor data and images
    
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
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
        
        # Upload image to S3
        s3_image_link = upload_image_to_s3(
            body['image'],
            body['device_id']
        )
        
        # Prepare data for DynamoDB
        dynamo_data = {
            'device_id': body['device_id'],
            'model_id': body['model_id'],
            'timestamp': body.get('timestamp', datetime.utcnow().isoformat()),
            's3_image_link': s3_image_link
        }
        
        # Store data in DynamoDB
        return store_sensor_data(dynamo_data)
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }