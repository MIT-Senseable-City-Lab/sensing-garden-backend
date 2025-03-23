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
import post_endpoints
import get_endpoints
import model_endpoints

# Add lambda/src to the Python path so we can import the schema
sys.path.append(os.path.join(os.path.dirname(__file__), 'lambda/src'))

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# The endpoint modules handle their own configuration via environment variables

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

def create_test_payload(request_type, device_id, model_id, timestamp):
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
            elif request_type == 'detection_request':
                if field == 'bounding_box':
                    payload[field] = [0.0, 0.0, 1.0, 1.0]  # Example bounding box coordinates
    except KeyError as e:
        print(f"Error creating payload: Missing key {str(e)}")
        sys.exit(1)

    # Add optional fields
    payload['timestamp'] = timestamp
    
    return payload

def test_post_endpoint(endpoint_type, device_id, model_id, timestamp):
    """Test a POST API endpoint (detection or classification) using endpoints.py"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = datetime.now().isoformat()
    
    # Determine which endpoint to use
    is_detection = endpoint_type == 'detection'
    
    # The endpoint modules now handle the API key internally
    
    print(f"\n\nTesting {endpoint_type.upper()} POST with device_id: {device_id}, model_id: {model_id}")
    
    # Create test image bytes
    image_data = create_test_image()
    
    try:
        # Call the appropriate write endpoint function
        print(f"\nSending {endpoint_type} write request to API using post_endpoints.py")
        if is_detection:
            response_data = post_endpoints.send_detection_request(
                device_id=device_id,
                model_id=model_id,
                image_data=image_data,
                timestamp=request_timestamp,
                bounding_box=[0.0, 0.0, 1.0, 1.0]  # Example bounding box coordinates
            )
        else:
            response_data = post_endpoints.send_classification_request(
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
            
    except requests.exceptions.RequestException as e:
        print(f"❌ {endpoint_type.capitalize()} API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    finally:
        # No patching needed anymore
        pass
    
    return success, request_timestamp

def test_post_detection(device_id, model_id, timestamp):
    """Test the detection API POST endpoint"""
    success, timestamp = test_post_endpoint('detection', device_id, model_id, timestamp)
    return success, timestamp

def test_post_classification(device_id, model_id, timestamp):
    """Test the classification API POST endpoint"""
    success, timestamp = test_post_endpoint('classification', device_id, model_id, timestamp)
    return success, timestamp

def add_test_data(device_id, model_id, timestamp, num_entries=10):
    """Add test data for detections and classifications"""
    detection_success = 0
    classification_success = 0
    
    print(f"\nAdding {num_entries} detection and {num_entries} classification records for device: {device_id}")
    
    for i in range(num_entries):
        print(f"\nCreating entry #{i+1}/{num_entries}")
        success, _ = test_post_endpoint('detection', device_id, model_id, timestamp)
        if success:
            detection_success += 1
        success, _ = test_post_endpoint('classification', device_id, model_id, timestamp)
        if success:
            classification_success += 1
    
    print(f"\n\nSummary:\n  - Detection entries: {detection_success}/{num_entries} created successfully")
    print(f"  - Classification entries: {classification_success}/{num_entries} created successfully")

def test_post_model(device_id, model_id, timestamp):
    """Test the model API POST endpoint using endpoints.py"""
    # Generate a unique version for this request to avoid conflicts
    version = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # The endpoint modules now handle the API key internally
    
    success = False
    try:
        # Call the model creation endpoint function
        print(f"\nSending model creation request to API using model_endpoints.py")
        
        # Create metadata for testing
        metadata = {
            'type': 'universal',
            'test_timestamp': datetime.now().isoformat()
        }
        
        # Call updated send_model_request function with all required parameters
        response_data = model_endpoints.send_model_request(
            model_id=model_id,
            device_id=device_id,
            name='Universal Test Model',
            version=version,
            description='A test model that can be used for both detection and classification',
            metadata=metadata,
            timestamp=timestamp
        )
        
        print(f"Response body: {json.dumps(response_data, indent=2)}")
        print(f"\n✅ Model API write request successful!")
        success = True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Model API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    finally:
        # No patching needed anymore
        pass
    
    return success

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API POST endpoints')
    parser.add_argument('--model', action='store_true', help='Test model API POST endpoints')
    parser.add_argument('--detection', action='store_true', help='Test detection API POST endpoints')
    parser.add_argument('--classification', action='store_true', help='Test classification API POST endpoints')
    parser.add_argument('--data', action='store_true', help='Add test data')
    parser.add_argument('--count', type=int, default=10, help='Number of test entries to create')
    parser.add_argument('--device', type=str, default="test-device", help='Device ID to use')
    parser.add_argument('--model-id', type=str, default="test-model-2025", help='Model ID to use')
    args = parser.parse_args()
    
    # Set device and model IDs
    device_id = args.device
    model_id = args.model_id
    timestamp = datetime.utcnow().isoformat()
    
    # If no specific arguments provided, run all tests
    run_all = not (args.model or args.detection or args.classification or args.data)
    
    # Test model API if requested
    if args.model or run_all:
        print("\nTesting model API POST endpoint...")
        model_success = test_post_model(device_id, model_id, timestamp)
        
        if not model_success and run_all:
            print("Failed to test model API POST endpoint. Exiting.")
            sys.exit(1)
    
    # Test detection API if requested
    if args.detection or run_all:
        print("\nTesting detection API POST endpoint...")
        detection_success, _ = test_post_detection(device_id, model_id, timestamp)
        
        if not detection_success and run_all:
            print("Failed to test detection API POST endpoint. Exiting.")
            sys.exit(1)
    
    # Test classification API if requested
    if args.classification or run_all:
        print("\nTesting classification API POST endpoint...")
        classification_success, _ = test_post_classification(device_id, model_id, timestamp)
        
        if not classification_success and run_all:
            print("Failed to test classification API POST endpoint. Exiting.")
            sys.exit(1)
    
    # Add test data if requested
    if args.data or run_all:
        add_test_data(device_id, model_id, timestamp, args.count)
    
    print("\nPOST API Tests completed.")
