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
import sys

# Add lambda/src to the Python path so we can import the schema
sys.path.append(os.path.join(os.path.dirname(__file__), 'lambda/src'))

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Import configuration from separate file or environment variables
def load_config():
    try:
        from config import API_ENDPOINT, API_KEY, AWS_REGION
        
        # Define the specific endpoints based on the base API_ENDPOINT
        DETECTION_API_ENDPOINT = f"{API_ENDPOINT.rstrip('/data')}/detections"
        CLASSIFICATION_API_ENDPOINT = f"{API_ENDPOINT.rstrip('/data')}/classifications"
        
    except ImportError:
        # Fallback to environment variables if config file doesn't exist
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
    
    print(f"Using API endpoints:")
    print(f"  Detection API: {DETECTION_API_ENDPOINT}")
    print(f"  Classification API: {CLASSIFICATION_API_ENDPOINT}")
    
    return {
        'api_key': API_KEY,
        'aws_region': AWS_REGION,
        'detection_endpoint': DETECTION_API_ENDPOINT,
        'classification_endpoint': CLASSIFICATION_API_ENDPOINT
    }

# Load configuration
config = load_config()
API_KEY = config['api_key']
AWS_REGION = config['aws_region']
DETECTION_API_ENDPOINT = config['detection_endpoint']
CLASSIFICATION_API_ENDPOINT = config['classification_endpoint']

# Define constants
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'
IMAGES_BUCKET = 'sensing-garden-images'
MODELS_TABLE = 'models'

# Load schema
def load_schema():
    """Load the schema from the lambda/src directory"""
    schema_path = os.path.join(os.path.dirname(__file__), 'lambda/src/schema.json')
    with open(schema_path, 'r') as f:
        return json.load(f)

# Get schema
try:
    SCHEMA = load_schema()
    print("Schema loaded successfully.")
    print("Schema keys:", SCHEMA.keys())
except KeyError as e:
    print(f"Error loading schema: Missing key {str(e)}")
    sys.exit(1)

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

def create_test_payload(request_type):
    """Create a test payload based on schema requirements"""
    payload = {}
    
    # Add required fields from schema
    try:
        api_schema = SCHEMA['properties']['api']['properties'][request_type]
        for field in api_schema['required']:
            if field == 'device_id':
                payload[field] = device_id
            elif field == 'model_id':
                payload[field] = model_id
            elif field == 'image':
                payload[field] = create_test_image()
            elif request_type == 'classification_request':
                if field == 'family':
                    payload[field] = "Test Family"
                elif field == 'genus':
                    payload[field] = "Test Genus"
                elif field == 'species':
                    payload[field] = "Test Species"
                elif field == 'family_confidence':
                    payload[field] = str(Decimal('0.92'))
                elif field == 'genus_confidence':
                    payload[field] = str(Decimal('0.94'))
                elif field == 'species_confidence':
                    payload[field] = str(Decimal('0.90'))
    except KeyError as e:
        print(f"Error creating payload: Missing key {str(e)}")
        sys.exit(1)

    # Add optional fields
    payload['timestamp'] = timestamp
    
    return payload

def test_api_endpoint(endpoint_type):
    """Test an API endpoint (detection or classification)"""
    # Determine which endpoint and table to use
    is_detection = endpoint_type == 'detection'
    request_type = 'detection_request' if is_detection else 'classification_request'
    endpoint = DETECTION_API_ENDPOINT if is_detection else CLASSIFICATION_API_ENDPOINT
    table_name = DETECTIONS_TABLE if is_detection else CLASSIFICATIONS_TABLE
    s3_prefix = 'detections' if is_detection else 'classifications'
    
    # Create payload and send request
    payload = create_test_payload(request_type)
    print(f"\n\nTesting {endpoint_type.upper()} with device_id: {device_id}, model_id: {model_id}")
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }
    
    print(f"\n1. Sending {endpoint_type} request to API: {endpoint}")
    response = requests.post(endpoint, json=payload, headers=headers)
    
    print(f"Response status code: {response.status_code}")
    print(f"Response body: {response.text}")
    
    # Check if successful
    if response.status_code == 200:
        print(f"\n✅ {endpoint_type.capitalize()} API request successful!")
        
        # Verify data in DynamoDB
        print(f"\n2. Checking DynamoDB for stored {endpoint_type} data...")
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(table_name)
        
        try:
            db_response = table.get_item(
                Key={
                    'device_id': device_id,
                    'timestamp': timestamp
                }
            )
            
            if 'Item' in db_response:
                print(f"✅ {endpoint_type.capitalize()} data found in DynamoDB!")
                print(f"DynamoDB item: {json.dumps(db_response['Item'], indent=2, cls=DecimalEncoder)}")
            else:
                print(f"❌ {endpoint_type.capitalize()} data not found in DynamoDB")
        except Exception as e:
            print(f"❌ Error checking DynamoDB: {str(e)}")
        
        # Check S3 for the image
        print(f"\n3. Checking S3 for uploaded {endpoint_type} image...")
        s3 = boto3.client('s3', region_name=AWS_REGION)
        
        try:
            # List objects in the bucket with the device_id prefix
            s3_response = s3.list_objects_v2(
                Bucket=IMAGES_BUCKET,
                Prefix=f"{s3_prefix}/{device_id}"
            )
            
            if 'Contents' in s3_response and len(s3_response['Contents']) > 0:
                print(f"✅ {endpoint_type.capitalize()} image found in S3!")
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
                print(f"❌ {endpoint_type.capitalize()} image not found in S3")
        except Exception as e:
            print(f"❌ Error checking S3: {str(e)}")
    else:
        print(f"❌ {endpoint_type.capitalize()} API request failed with status code: {response.status_code}")
    
    return response.status_code == 200

def test_detection():
    """Test the detection API endpoint"""
    return test_api_endpoint('detection')

def test_classification():
    """Test the classification API endpoint"""
    return test_api_endpoint('classification')

def add_test_data(device_id, num_entries=10):
    """Add test data for detections and classifications"""
    for _ in range(num_entries):
        test_api_endpoint('detection')
        test_api_endpoint('classification')

def add_models():
    """Add test models to the models table"""
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    models_table = dynamodb.Table(MODELS_TABLE)

    models = [
        {
            'id': str(uuid.uuid4()), 
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0',
            'description': 'Test Detection Model A',
            'type': 'detection'
        },
        {
            'id': str(uuid.uuid4()), 
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.1',
            'description': 'Test Classification Model B',
            'type': 'classification'
        }
    ]

    for model in models:
        models_table.put_item(Item=model)
        print(f"Added model: {model['id']} version {model['version']} ({model['type']})")

if __name__ == "__main__":
    # Example device_id to use for testing
    device_id = "test-device-a509497e"
    model_id = "example-model-id"
    timestamp = datetime.now().isoformat()

    # Add test data
    add_test_data(device_id)

    # Add test models
    add_models()

    print("Test data and models added successfully.")
