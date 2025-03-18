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

import requests
from PIL import Image, ImageDraw

# Import the endpoints modules
import endpoints
import read_endpoints

# Add lambda/src to the Python path so we can import the schema
sys.path.append(os.path.join(os.path.dirname(__file__), 'lambda/src'))

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Configuration variables
API_KEY = os.environ.get("SENSING_GARDEN_API_KEY", "gMVUsSGzdZ5JgLgpadHtA9yd3Jz5THYs2pEPP7Al")

# API endpoints
API_BASE = os.environ.get("API_BASE_URL", "https://80tryunqte.execute-api.us-east-1.amazonaws.com")

# Update base URL in endpoints modules
endpoints.BASE_URL = API_BASE
read_endpoints.set_base_url(API_BASE)

# Print configuration information
print(f"Using API endpoint base URL: {API_BASE}")

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
    """Test an API endpoint (detection or classification) using endpoints.py and read_endpoints.py"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = datetime.now().isoformat()
    
    # Determine which endpoint to use
    is_detection = endpoint_type == 'detection'
    
    # Create a custom function to include the API key in headers for both GET and POST requests
    def _add_api_key_to_requests_post(url, **kwargs):
        # Make sure headers exist in kwargs
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        
        # Add API key to headers
        kwargs['headers']['x-api-key'] = API_KEY
        
        # Call the original requests.post with all arguments
        return original_post(url, **kwargs)
    
    def _add_api_key_to_requests_get(url, **kwargs):
        # Make sure headers exist in kwargs
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        
        # Add API key to headers
        kwargs['headers']['x-api-key'] = API_KEY
        
        # Call the original requests.get with all arguments
        return original_get(url, **kwargs)
    
    # Patch the requests methods
    original_post = requests.post
    original_get = requests.get
    requests.post = _add_api_key_to_requests_post
    requests.get = _add_api_key_to_requests_get
    
    print(f"\n\nTesting {endpoint_type.upper()} with device_id: {device_id}, model_id: {model_id}")
    
    # Create test image bytes
    image_data = create_test_image()
    
    try:
        # STEP 1: Call the appropriate write endpoint function
        print(f"\n1. Sending {endpoint_type} write request to API using endpoints.py")
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
        print(f"\n✅ {endpoint_type.capitalize()} API write request successful!")
        success = True
        
        # STEP 2: Verify data through read API if the write was successful
        print(f"\n2. Verifying data through read API using read_endpoints.py...")
        
        # Use the appropriate read endpoint function
        if is_detection:
            data = read_endpoints.get_detections(
                device_id=device_id,
                start_time=request_timestamp,
                end_time=datetime.now().isoformat(),
                limit=10
            )
        else:
            data = read_endpoints.get_classifications(
                device_id=device_id,
                start_time=request_timestamp,
                end_time=datetime.now().isoformat(),
                limit=10
            )
        
        # Check if our item is in the results
        if data.get('items'):
            item = next((item for item in data['items'] if item.get('timestamp') == request_timestamp), None)
            if item:
                print(f"✅ {endpoint_type.capitalize()} data found through API!")
                print(f"API response: {json.dumps(item, indent=2, cls=DecimalEncoder)}")
                
                # Check for image URL
                if 'image_url' in item:
                    print(f"✅ Image URL found in API response: {item['image_url']}")
                else:
                    print(f"❌ No image URL found in the API response")
            else:
                print(f"❌ {endpoint_type.capitalize()} data not found through API")
                success = False
        else:
            print(f"❌ No items returned from the API")
            success = False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ {endpoint_type.capitalize()} API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    finally:
        # Restore the original requests methods
        requests.post = original_post
        requests.get = original_get
    
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
    """Add one test model and verify using read_endpoints.py"""
    # Create test model data
    timestamp = datetime.utcnow().isoformat()
    model_data = {
        'device_id': device_id,
        'model_id': model_id,
        'timestamp': timestamp,
        'name': 'Universal Test Model',
        'description': 'A test model that can be used for both detection and classification',
        'version': '1.0',
        'metadata': {
            'type': 'universal'
        }
    }
    
    # Create functions to patch requests to include API key
    def _add_api_key_to_requests_post(url, **kwargs):
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers']['x-api-key'] = API_KEY
        return original_post(url, **kwargs)
    
    def _add_api_key_to_requests_get(url, **kwargs):
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers']['x-api-key'] = API_KEY
        return original_get(url, **kwargs)
    
    # Patch requests methods
    original_post = requests.post
    original_get = requests.get
    requests.post = _add_api_key_to_requests_post
    requests.get = _add_api_key_to_requests_get
    
    try:
        # STEP 1: Add model through the API directly
        print(f"\n1. Creating model {model_id}...")
        response = requests.post(
            f"{API_BASE}/models",
            json=model_data,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        result = response.json()
        print(f"✅ Model created: {model_data['model_id']} version {model_data['version']}")
        print(f"Response: {json.dumps(result, indent=2)}")
        
        # STEP 2: Verify model was added by reading it back using read_endpoints
        print(f"\n2. Verifying model using read_endpoints.py...")
        models = read_endpoints.get_models(
            device_id=device_id,
            model_id=model_id
        )
        
        if models.get('items') and len(models['items']) > 0:
            model = models['items'][0]
            print(f"✅ Model verified through API!")
            print(f"API response: {json.dumps(model, indent=2, cls=DecimalEncoder)}")
            return True
        else:
            print(f"❌ Failed to verify model through API")
            return False
    except Exception as e:
        print(f"❌ Error adding/verifying model: {str(e)}")
        return False
    finally:
        # Restore original requests methods
        requests.post = original_post
        requests.get = original_get

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API')
    parser.add_argument('--model', action='store_true', help='Test model API')
    parser.add_argument('--data', action='store_true', help='Add test data')
    parser.add_argument('--count', type=int, default=10, help='Number of test entries to create')
    parser.add_argument('--device', type=str, default="test-device", help='Device ID to use')
    parser.add_argument('--model-id', type=str, default="test-model-2025", help='Model ID to use')
    args = parser.parse_args()
    
    # Set device and model IDs
    device_id = args.device
    model_id = args.model_id
    
    # If no specific arguments provided, run all tests
    run_all = not (args.model or args.data)
    
    # Add test model if requested
    if args.model or run_all:
        print("\nCreating test model...")
        model_success = add_models()
        
        if not model_success and run_all:
            print("Failed to create model. Exiting.")
            sys.exit(1)
    
    # Add test data if requested
    if args.data or run_all:
        add_test_data(args.count)
    
    print("\nTest completed.")
