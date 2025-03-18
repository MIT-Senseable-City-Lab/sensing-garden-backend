#!/usr/bin/env python3
import argparse
import base64
import io
import json
import os
import sys
import uuid
from datetime import datetime
from decimal import Decimal

import boto3
import requests
from PIL import Image, ImageDraw

# Import the endpoints module
import endpoints

# Add lambda/src to the Python path so we can import the schema
sys.path.append(os.path.join(os.path.dirname(__file__), 'lambda/src'))

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Configuration variables
AWS_REGION = os.environ.get("SENSING_GARDEN_AWS_REGION", "us-east-1")
API_KEY = os.environ.get("SENSING_GARDEN_API_KEY", "your-api-key-here")

# Hardcoded API endpoints
API_BASE = "https://9cgp0r5jh3.execute-api.us-east-1.amazonaws.com"
DETECTION_API_ENDPOINT = f"{API_BASE}/detection"
CLASSIFICATION_API_ENDPOINT = f"{API_BASE}/classification"

# Print configuration information
print(f"Using AWS Region: {AWS_REGION}")
print(f"Using API endpoints:")
print(f"  Detection API: {DETECTION_API_ENDPOINT}")
print(f"  Classification API: {CLASSIFICATION_API_ENDPOINT}")

# Define constants
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'
MODELS_TABLE = 'models'

# Load schema
def load_schema():
    """Load the API schema from the common directory"""
    schema_path = os.path.join(os.path.dirname(__file__), 'common/api-schema.json')
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            print("Schema loaded successfully.")
            print("Schema keys:", schema.keys())
            return schema
    except FileNotFoundError:
        error_msg = f"API schema file not found at {schema_path}"
        print(error_msg)
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in schema file {schema_path}: {str(e)}"
        print(error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Failed to load schema from {schema_path}: {str(e)}"
        print(error_msg)
        sys.exit(1)

# Load the schema
SCHEMA = load_schema()

# Create a test image
def create_test_image():
    # Create a simple image with text
    img = Image.new('RGB', (300, 200), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10,10), f"Test Image {datetime.now().isoformat()}", fill=(255,255,0))
    
    # Save to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    
    # Return raw bytes (not base64 encoded)
    return img_byte_arr.getvalue()

def create_test_payload(request_type):
    """Create a test payload based on schema requirements"""
    payload = {}
    
    # Map request types to OpenAPI schema components
    schema_type_map = {
        'detection_request': 'DetectionData',
        'classification_request': 'ClassificationData'
    }
    
    # Add required fields from schema
    try:
        api_schema = SCHEMA['components']['schemas'][schema_type_map[request_type]]
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
    """Test an API endpoint (detection or classification) using endpoints.py"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = datetime.now().isoformat()
    
    # Determine which endpoint and table to use
    is_detection = endpoint_type == 'detection'
    table_name = DETECTIONS_TABLE if is_detection else CLASSIFICATIONS_TABLE
    
    # Update the base URL in endpoints module
    endpoints.BASE_URL = API_BASE
    
    # Create a custom function to include the API key in headers
    def _add_api_key_to_requests(url, json_data, headers):
        # Add API key to headers
        headers["x-api-key"] = API_KEY
        return requests.post(url, json=json_data, headers=headers)
    
    # Patch the requests.post method in endpoints module
    original_post = requests.post
    requests.post = _add_api_key_to_requests
    
    print(f"\n\nTesting {endpoint_type.upper()} with device_id: {device_id}, model_id: {model_id}")
    
    # Create test image bytes
    image_data = create_test_image()
    
    # Call the appropriate endpoint function
    print(f"\n1. Sending {endpoint_type} request to API using endpoints.py")
    try:
        if is_detection:
            response_data = endpoints.send_detection_request(
                device_id=device_id,
                model_id=model_id,
                image_data=image_data,
                timestamp=request_timestamp
            )
        else:
            response_data = endpoints.send_classification_request(
                device_id=device_id,
                model_id=model_id,
                image_data=image_data,
                family="Test Family",
                genus="Test Genus",
                species="Test Species",
                family_confidence=0.92,
                genus_confidence=0.94,
                species_confidence=0.90,
                timestamp=request_timestamp
            )
        
        print(f"Response body: {json.dumps(response_data, indent=2)}")
        print(f"\n✅ {endpoint_type.capitalize()} API request successful!")
        success = True
    except requests.exceptions.RequestException as e:
        print(f"❌ {endpoint_type.capitalize()} API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
        response_data = None
    finally:
        # Restore the original requests.post method
        requests.post = original_post
    
    # Verify data in DynamoDB if successful
    if success:
        print(f"\n2. Checking DynamoDB for stored {endpoint_type} data...")
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(table_name)
        
        try:
            db_response = table.get_item(
                Key={
                    'device_id': device_id,
                    'timestamp': request_timestamp
                }
            )
            
            if 'Item' in db_response:
                print(f"✅ {endpoint_type.capitalize()} data found in DynamoDB!")
                print(f"DynamoDB item: {json.dumps(db_response['Item'], indent=2, cls=DecimalEncoder)}")
            else:
                print(f"❌ {endpoint_type.capitalize()} data not found in DynamoDB")
        except Exception as e:
            print(f"❌ Error checking DynamoDB: {str(e)}")
        
        # Just log the image_key information from DynamoDB
        if 'Item' in db_response and 'image_key' in db_response['Item']:
            image_key = db_response['Item']['image_key']
            print(f"✅ Image key found in DynamoDB: {image_key}")
        else:
            print(f"❌ No image_key found in the DynamoDB item")
    
    return success

def test_detection():
    """Test the detection API endpoint"""
    return test_api_endpoint('detection')

def test_classification():
    """Test the classification API endpoint"""
    return test_api_endpoint('classification')

def add_test_data(num_entries=10):
    """Add test data for detections and classifications"""
    detection_success = 0
    classification_success = 0
    
    print(f"\nAdding {num_entries} detection and {num_entries} classification records for device: {device_id}")
    
    for i in range(num_entries):
        print(f"\nCreating entry #{i+1}/{num_entries}")
        if test_api_endpoint('detection'):
            detection_success += 1
        if test_api_endpoint('classification'):
            classification_success += 1
    
    print(f"\n\nSummary:\n  - Detection entries: {detection_success}/{num_entries} created successfully")
    print(f"  - Classification entries: {classification_success}/{num_entries} created successfully")

def add_models():
    """Add one test model to the models table"""
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    models_table = dynamodb.Table(MODELS_TABLE)

    # Create a single test model that can be used for both detection and classification
    model = {
        'id': model_id, 
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0',
        'description': 'Universal Test Model',
        'type': 'universal'
    }

    try:
        models_table.put_item(Item=model)
        print(f"Added model: {model['id']} version {model['version']} ({model['type']})")
        return True
    except Exception as e:
        print(f"Error adding model: {str(e)}")
        return False

if __name__ == "__main__":
    # Hardcoded test device and model
    device_id = "test-device"
    model_id = "test-model-2025"

    # Add one test model
    print("\nCreating test model...")
    model_success = add_models()
    
    if not model_success:
        print("Failed to create model. Exiting.")
        sys.exit(1)
    
    # Add 10 test data entries each for detection and classification
    add_test_data(10)
    
    print("\nTest setup completed successfully.")
