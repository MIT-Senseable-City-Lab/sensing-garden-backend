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

# Import the Sensing Garden client package
from sensing_garden_client import SensingGardenClient, get_models, get_detections, get_classifications, \
    send_detection_request, send_classification_request, send_model_request
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

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

# This function is no longer needed as we're using the client API directly

def test_post_endpoint(endpoint_type, device_id, model_id, timestamp):
    """Test a POST API endpoint (detection or classification) using sensing_garden_api package"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = datetime.now().isoformat()
    
    # Determine which endpoint to use
    is_detection = endpoint_type == 'detection'
    
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
    print(f"\n\nTesting {endpoint_type.upper()} POST with device_id: {device_id}, model_id: {model_id}")
    
    # Create test image bytes
    image_data = create_test_image()
    
    try:
        # Call the appropriate write endpoint function
        print(f"\nSending {endpoint_type} write request to API using sensing_garden_api package")
        if is_detection:
            response_data = send_detection_request(
                client=client,
                device_id=device_id,
                model_id=model_id,
                image_data=image_data,
                timestamp=request_timestamp,
                bounding_box=[0.0, 0.0, 1.0, 1.0]  # Example bounding box coordinates
            )
        else:
            response_data = send_classification_request(
                client=client,
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

def test_post_detection_with_invalid_model(device_id, timestamp):
    """Test the detection API POST endpoint with an invalid model_id"""
    # Create a random UUID that won't exist in the database
    invalid_model_id = str(uuid.uuid4())
    print(f"\nTesting DETECTION POST with invalid model_id: {invalid_model_id}")
    
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
    # Create test image bytes
    image_data = create_test_image()
    request_timestamp = datetime.now().isoformat()
    
    try:
        # Try to send a detection with an invalid model_id
        response_data = send_detection_request(
            client=client,
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            timestamp=request_timestamp,
            bounding_box=[0.0, 0.0, 1.0, 1.0]
        )
        
        # If we get here without an exception, the test failed
        print(f"❌ Detection with invalid model_id succeeded but should have failed!")
        print(f"Response: {json.dumps(response_data, indent=2)}")
        return False
            
    except requests.exceptions.RequestException as e:
        # We expect an error, so this is success
        print(f"✅ Detection with invalid model_id failed as expected!")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return True
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False

def test_post_classification(device_id, model_id, timestamp):
    """Test the classification API POST endpoint"""
    success, timestamp = test_post_endpoint('classification', device_id, model_id, timestamp)
    return success, timestamp

def test_post_classification_with_invalid_model(device_id, timestamp):
    """Test the classification API POST endpoint with an invalid model_id"""
    # Create a random UUID that won't exist in the database
    invalid_model_id = str(uuid.uuid4())
    print(f"\nTesting CLASSIFICATION POST with invalid model_id: {invalid_model_id}")
    
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
    # Create test image bytes
    image_data = create_test_image()
    request_timestamp = datetime.now().isoformat()
    
    try:
        # Try to send a classification with an invalid model_id
        response_data = send_classification_request(
            client=client,
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            family="Test Family",
            genus="Test Genus",
            species="Test Species",
            family_confidence=0.92,
            genus_confidence=0.94,
            species_confidence=0.90,
            timestamp=request_timestamp
        )
        
        # If we get here without an exception, the test failed
        print(f"❌ Classification with invalid model_id succeeded but should have failed!")
        print(f"Response: {json.dumps(response_data, indent=2)}")
        return False
            
    except requests.exceptions.RequestException as e:
        # We expect an error, so this is success
        print(f"✅ Classification with invalid model_id failed as expected!")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return True
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False

def add_test_data(device_id, model_id, timestamp, num_entries=10):
    """Add test data for detections and classifications"""
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
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
    """Test the model API POST endpoint using sensing_garden_api package"""
    # Generate a unique version for this request to avoid conflicts
    version = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
    success = False
    try:
        # Call the model creation endpoint function
        print(f"\nSending model creation request to API using sensing_garden_api package")
        
        # Create metadata for testing
        metadata = {
            'type': 'universal',
            'test_timestamp': datetime.now().isoformat()
        }
        
        # Call updated send_model_request function with all required parameters
        response_data = send_model_request(
            client=client,
            model_id=model_id,
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
    parser.add_argument('--test-invalid-model', action='store_true', help='Test validation for non-existent model_id')
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
    
    # Test validation of non-existent model_id if requested
    if args.test_invalid_model:
        print("\nTesting validation of non-existent model_id...")
        detection_test_success = test_post_detection_with_invalid_model(device_id, timestamp)
        classification_test_success = test_post_classification_with_invalid_model(device_id, timestamp)
        
        if detection_test_success and classification_test_success:
            print("\n✅ Model validation tests PASSED!")
        else:
            print("\n❌ Model validation tests FAILED!")
    
    print("\nPOST API Tests completed.")
