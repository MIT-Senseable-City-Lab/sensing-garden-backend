#!/usr/bin/env python3
import requests
import json
import base64
import uuid
import boto3
from datetime import datetime
import os
from PIL import Image, ImageDraw
import io
import argparse
from decimal import Decimal

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Import configuration from separate file (excluded from git)
try:
    from config import API_ENDPOINT, API_KEY, AWS_REGION
    
    # Define the specific endpoints based on the base API_ENDPOINT
    DETECTION_API_ENDPOINT = f"{API_ENDPOINT.rstrip('/data')}/detections"
    CLASSIFICATION_API_ENDPOINT = f"{API_ENDPOINT.rstrip('/data')}/classifications"
    
    print(f"Using API endpoints from config:")
    print(f"  Base API: {API_ENDPOINT}")
    print(f"  Detection API: {DETECTION_API_ENDPOINT}")
    print(f"  Classification API: {CLASSIFICATION_API_ENDPOINT}")
    
except ImportError:
    # Fallback to environment variables if config file doesn't exist
    import os
    API_ENDPOINT = os.environ.get("SENSING_GARDEN_API_ENDPOINT")
    API_KEY = os.environ.get("SENSING_GARDEN_API_KEY")
    AWS_REGION = os.environ.get("SENSING_GARDEN_AWS_REGION", "us-east-1")
    
    # Use the specific endpoints from Terraform output
    DETECTION_API_ENDPOINT = "https://9cgp0r5jh3.execute-api.us-east-1.amazonaws.com/detections"
    CLASSIFICATION_API_ENDPOINT = "https://9cgp0r5jh3.execute-api.us-east-1.amazonaws.com/classifications"
    
    if not API_KEY:
        raise ValueError(
            "API configuration not found. Either create a config.py file or "
            "set the following environment variables:\n"
            "- SENSING_GARDEN_API_KEY\n"
            "- SENSING_GARDEN_AWS_REGION (optional)"
        )

# Define constants
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'
IMAGES_BUCKET = 'sensing-garden-images'

# Create a test image
def create_test_image():
    # Create a simple image with text
    img = Image.new('RGB', (300, 200), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10,10), f"Test Image {datetime.now().isoformat()}", fill=(255,255,0))
    
    # Save to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr = img_byte_arr.getvalue()
    
    # Encode as base64
    return base64.b64encode(img_byte_arr).decode('utf-8')

def test_detection():
    # Create test payload for detection
    detection_payload = {
        "device_id": device_id,
        "model_id": model_id,
        "timestamp": timestamp,
        "image": create_test_image()
    }
    
    print(f"Testing DETECTION with device_id: {device_id}, model_id: {model_id}")
    
    # Send request to API
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }
    
    # Use the specific detection endpoint from Terraform output
    detection_endpoint = DETECTION_API_ENDPOINT
    print(f"\n1. Sending detection request to API: {detection_endpoint}")
    response = requests.post(detection_endpoint, json=detection_payload, headers=headers)
    
    print(f"Response status code: {response.status_code}")
    print(f"Response body: {response.text}")
    
    # Check if successful
    if response.status_code == 200:
        print("\n✅ Detection API request successful!")
        
        # Verify data in DynamoDB
        print("\n2. Checking DynamoDB for stored detection data...")
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(DETECTIONS_TABLE)
        
        try:
            db_response = table.get_item(
                Key={
                    'device_id': device_id,
                    'timestamp': timestamp
                }
            )
            
            if 'Item' in db_response:
                print("✅ Detection data found in DynamoDB!")
                print(f"DynamoDB item: {json.dumps(db_response['Item'], indent=2, cls=DecimalEncoder)}")
            else:
                print("❌ Detection data not found in DynamoDB")
        except Exception as e:
            print(f"❌ Error checking DynamoDB: {str(e)}")
        
        # Check S3 for the image
        print("\n3. Checking S3 for uploaded detection image...")
        s3 = boto3.client('s3', region_name=AWS_REGION)
        
        try:
            # List objects in the bucket with the device_id prefix
            s3_response = s3.list_objects_v2(
                Bucket=IMAGES_BUCKET,
                Prefix=f"detections/{device_id}"
            )
            
            if 'Contents' in s3_response and len(s3_response['Contents']) > 0:
                print("✅ Detection image found in S3!")
                for obj in s3_response['Contents']:
                    print(f"S3 object: {obj['Key']}, Size: {obj['Size']} bytes")
                    # Generate a presigned URL for viewing the image
                    url = s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': IMAGES_BUCKET, 'Key': obj['Key']},
                        ExpiresIn=3600
                    )
                    print(f"Image URL (valid for 1 hour): {url}")
            else:
                print("❌ Detection image not found in S3")
        except Exception as e:
            print(f"❌ Error checking S3: {str(e)}")
    else:
        print(f"❌ Detection API request failed with status code: {response.status_code}")
    return response.status_code == 200

def test_classification():
    # Create test payload for classification with additional fields
    classification_payload = {
        "device_id": device_id,
        "model_id": model_id,
        "timestamp": timestamp,
        "image": create_test_image(),
        "genus": "Test Genus",
        "family": "Test Family",
        "species": "Test Species",
        "confidence": str(Decimal('0.95'))  # Convert to string for JSON serialization
    }
    
    print(f"\n\nTesting CLASSIFICATION with device_id: {device_id}, model_id: {model_id}")
    
    # Send request to API
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }
    
    # Use the specific classification endpoint from Terraform output
    classification_endpoint = CLASSIFICATION_API_ENDPOINT
    print(f"\n1. Sending classification request to API: {classification_endpoint}")
    response = requests.post(classification_endpoint, json=classification_payload, headers=headers)

    print(f"Response status code: {response.status_code}")
    print(f"Response body: {response.text}")
    
    # Check if successful
    if response.status_code == 200:
        print("\n✅ Classification API request successful!")
        
        # Verify data in DynamoDB
        print("\n2. Checking DynamoDB for stored classification data...")
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(CLASSIFICATIONS_TABLE)
        
        try:
            db_response = table.get_item(
                Key={
                    'device_id': device_id,
                    'timestamp': timestamp
                }
            )
            
            if 'Item' in db_response:
                print("✅ Classification data found in DynamoDB!")
                print(f"DynamoDB item: {json.dumps(db_response['Item'], indent=2, cls=DecimalEncoder)}")
            else:
                print("❌ Classification data not found in DynamoDB")
        except Exception as e:
            print(f"❌ Error checking DynamoDB: {str(e)}")
        
        # Check S3 for the image
        print("\n3. Checking S3 for uploaded classification image...")
        s3 = boto3.client('s3', region_name=AWS_REGION)
        
        try:
            # List objects in the bucket with the device_id prefix
            s3_response = s3.list_objects_v2(
                Bucket=IMAGES_BUCKET,
                Prefix=f"classifications/{device_id}"
            )
            
            if 'Contents' in s3_response and len(s3_response['Contents']) > 0:
                print("✅ Classification image found in S3!")
                for obj in s3_response['Contents']:
                    print(f"S3 object: {obj['Key']}, Size: {obj['Size']} bytes")
                    # Generate a presigned URL for viewing the image
                    url = s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': IMAGES_BUCKET, 'Key': obj['Key']},
                        ExpiresIn=3600
                    )
                    print(f"Image URL (valid for 1 hour): {url}")
            else:
                print("❌ Classification image not found in S3")
        except Exception as e:
            print(f"❌ Error checking S3: {str(e)}")
    else:
        print(f"❌ Classification API request failed with status code: {response.status_code}")
    return response.status_code == 200


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API')
    parser.add_argument('--test-type', choices=['detection', 'classification', 'both'], 
                        default='both', help='Type of test to run')
    args = parser.parse_args()
    
    # Generate a unique device ID and model ID for testing
    device_id = f"test-device-{uuid.uuid4().hex[:8]}"
    model_id = f"test-model-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now().isoformat()
    
    if args.test_type == 'detection' or args.test_type == 'both':
        test_detection()
        
    if args.test_type == 'classification' or args.test_type == 'both':
        test_classification()
