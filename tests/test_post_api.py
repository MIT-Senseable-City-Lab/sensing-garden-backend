#!/usr/bin/env python3
import argparse
import io
import json
import os
import random
import string
import sys
import uuid
from datetime import datetime
from decimal import Decimal

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw
# Import the Sensing Garden client package
from sensing_garden_client import SensingGardenClient

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

# Create a test video (simulated with a small binary file)
def create_test_video():
    # Create a simple binary file that simulates a video
    # In a real scenario, this would be actual video data
    video_data = bytearray([random.randint(0, 255) for _ in range(1024)])
    return bytes(video_data)

def generate_random_string(length=8):
    """Generate a random string of specified length"""
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def generate_random_confidence():
    """Generate a random confidence value between 0 and 1"""
    return random.uniform(0.5, 1.0)  # Ensure confidences are reasonable (above 0.5)

def generate_random_bounding_box():
    """Generate a random bounding box with coordinates between 0 and 1"""
    x1 = random.uniform(0, 0.8)  # Ensure room for width
    y1 = random.uniform(0, 0.8)  # Ensure room for height
    width = random.uniform(0.1, 0.8 - x1)  # Ensure valid width
    height = random.uniform(0.1, 0.8 - y1)  # Ensure valid height
    return [x1, y1, x1 + width, y1 + height]

# Predefined lists of test names
TEST_FAMILIES = [
    "test_family_rosaceae",
    "test_family_fabaceae",
    "test_family_salicaceae",
    "test_family_pinaceae"
]

TEST_GENERA = [
    "test_genus_prunus",
    "test_genus_quercus",
    "test_genus_salix",
    "test_genus_pinus"
]

TEST_SPECIES = [
    "test_species_prunus_persica",
    "test_species_quercus_robur",
    "test_species_salix_alba",
    "test_species_pinus_sylvestris"
]

def get_random_test_name(name_list):
    """Get a random name from the predefined list"""
    return random.choice(name_list)

def test_post_endpoint(endpoint_type, device_id, model_id, timestamp):
    """Test a POST API endpoint (detection or classification) using sensing_garden_api package"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = timestamp
    
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
            response_data = client.detections.add(
                device_id=device_id,
                model_id=model_id,
                image_data=image_data,
                timestamp=request_timestamp,
                bounding_box=generate_random_bounding_box()
            )
        else:
            response_data = client.classifications.add(
                device_id=device_id,
                model_id=model_id,
                image_data=image_data,
                family=get_random_test_name(TEST_FAMILIES),
                genus=get_random_test_name(TEST_GENERA),
                species=get_random_test_name(TEST_SPECIES),
                family_confidence=generate_random_confidence(),
                genus_confidence=generate_random_confidence(),
                species_confidence=generate_random_confidence(),
                timestamp=request_timestamp
            )
        
        print(f"Response body: {json.dumps(response_data, indent=2)}")
        print(f"\n✅ {endpoint_type.capitalize()} API write request successful!")
        assert True, f"{endpoint_type.capitalize()} API write request failed at {request_timestamp}"
            
    except requests.exceptions.RequestException as e:
        print(f"❌ {endpoint_type.capitalize()} API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        assert False, f"{endpoint_type.capitalize()} API request failed at {request_timestamp}"
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        assert False, f"{endpoint_type.capitalize()} API request failed at {request_timestamp}"

def test_post_detection(device_id, model_id, timestamp):
    """Test the detection API POST endpoint"""
    test_post_endpoint('detection', device_id, model_id, timestamp)

def test_post_detection_with_invalid_model(device_id, nonexistent_model_id, timestamp):
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
    request_timestamp = timestamp
    
    try:
        # Try to send a detection with a random/nonexistent model_id
        response_data = client.detections.add(
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            timestamp=request_timestamp,
            bounding_box=generate_random_bounding_box()
        )
        
        print(f"✅ Detection with random/nonexistent model_id succeeded as expected!")
        print(f"Response: {json.dumps(response_data, indent=2)}")
        assert True, f"Detection with random/nonexistent model_id succeeded at {request_timestamp}"
            
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        assert False, f"Detection with random/nonexistent model_id failed at {request_timestamp}"

def test_post_classification(device_id, model_id, timestamp):
    """Test the classification API POST endpoint"""
    test_post_endpoint('classification', device_id, model_id, timestamp)

def test_post_classification_with_invalid_model(device_id, nonexistent_model_id, timestamp):
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
    request_timestamp = timestamp
    
    try:
        # Try to send a classification with an invalid model_id
        response_data = client.classifications.add(
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            family=get_random_test_name(TEST_FAMILIES),
            genus=get_random_test_name(TEST_GENERA),
            species=get_random_test_name(TEST_SPECIES),
            family_confidence=generate_random_confidence(),
            genus_confidence=generate_random_confidence(),
            species_confidence=generate_random_confidence(),
            timestamp=request_timestamp
        )
        print(f"✅ Classification with random/nonexistent model_id succeeded as expected!")
        print(f"Response: {json.dumps(response_data, indent=2)}")
        assert True, f"Classification with random/nonexistent model_id succeeded at {request_timestamp}"
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        assert False, f"Classification with random/nonexistent model_id failed at {request_timestamp}"

def test_post_video(device_id, timestamp, video_file_path):
    """Test the video API POST endpoint"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = timestamp
    
    # Initialize the client with API key and base URL from environment
    from tests.test_utils import get_client
    client = get_client()
    
    print(f"\n\nTesting VIDEO POST with device_id: {device_id}")
    
    try:
        # If a video file path is provided and exists, use the upload_file method
        if video_file_path and os.path.exists(video_file_path):
            print(f"Using video file: {video_file_path} with direct S3 multipart upload")
            # Determine file size for logging
            file_size = os.path.getsize(video_file_path)
            print(f"Video file size: {file_size / (1024 * 1024):.2f} MB")
            
            # Use the upload_file method which handles S3 multipart uploads directly
            response_data = client.videos.upload_video(
                device_id=device_id,
                video_path_or_data=video_file_path,
                                timestamp=request_timestamp,
                metadata={"test": True, "source": "test_post_api.py"}
            )
        else:
            # If no file is provided, use the generated test data with standard upload
            print("No valid video file provided, using generated test data")
            video_data = create_test_video()
            
            # For small test videos, we can still use the direct upload method
            # Create a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_file.write(video_data)
                temp_file_path = temp_file.name
            
            try:
                # Use the upload_file method with the temporary file
                response_data = client.videos.upload_video(
                    device_id=device_id,
                    video_path_or_data=temp_file_path,
                                        timestamp=request_timestamp,
                    metadata={"test": True, "source": "test_post_api.py"}
                )
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        
        print(f"Response body: {json.dumps(response_data, indent=2)}")
        print(f"\n✅ Video API upload request successful!")
        success = True
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Video API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    
    assert success, f"POST endpoint failed at {request_timestamp}"

def test_post_classification_with_invalid_model(device_id, nonexistent_model_id, timestamp):
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
    request_timestamp = timestamp
    
    try:
        # Try to send a classification with an invalid model_id
        response_data = client.classifications.add(
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            family=get_random_test_name(TEST_FAMILIES),
            genus=get_random_test_name(TEST_GENERA),
            species=get_random_test_name(TEST_SPECIES),
            family_confidence=generate_random_confidence(),
            genus_confidence=generate_random_confidence(),
            species_confidence=generate_random_confidence(),
            timestamp=request_timestamp
        )
        print(f"✅ Classification with random/nonexistent model_id succeeded as expected!")
        print(f"Response: {json.dumps(response_data, indent=2)}")
        assert True, f"Classification with random/nonexistent model_id succeeded at {request_timestamp}"
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        assert False, f"Classification with random/nonexistent model_id failed at {request_timestamp}"

def add_test_data(device_id, model_id, timestamp, num_entries=10):
    """Add test data for detections, classifications, and videos"""
    print(f"\nAdding {num_entries} test entries for device {device_id}")
    
    for i in range(num_entries):
        # Rotate between detection, classification, and video
        if i % 3 == 0:
            test_post_detection(device_id, model_id, timestamp)
        elif i % 3 == 1:
            test_post_classification(device_id, model_id, timestamp)
        else:
            test_post_video(device_id, timestamp, None)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API POST endpoints')
    parser.add_argument('--device-id', type=str, required=True, help='Device ID to use for testing')
    parser.add_argument('--video-file', type=str, help='Path to a video file for video upload testing')
    parser.add_argument('--model-id', type=str, help='Model ID to use for testing')
    parser.add_argument('--timestamp', type=str, help='Optional timestamp to use for testing')
    parser.add_argument('--num-entries', type=int, default=10, help='Number of test entries to add')
    parser.add_argument('--video-only', action='store_true', help='Test only the video API endpoint')
    
    args = parser.parse_args()
    
    # Use provided timestamp or generate a new one
    timestamp = args.timestamp or datetime.now().isoformat()
    
    # Run the appropriate tests
    success = True
    
    # If only video testing is requested, skip other tests
    if args.video_only:
        video_success, _ = test_post_video(args.device_id, timestamp, args.video_file)
        success = video_success
    else:
        # Ensure model_id is provided for non-video-only tests
        if not args.model_id:
            print("Error: --model-id is required for detection and classification tests")
            sys.exit(1)
            
        # Test detection endpoints
        detection_success, _ = test_post_detection(args.device_id, args.model_id, timestamp)
        success &= detection_success
        detection_invalid_success, _ = test_post_detection_with_invalid_model(args.device_id, timestamp)
        success &= detection_invalid_success
    
    # Test classification endpoints
    classification_success, _ = test_post_classification(args.device_id, args.model_id, timestamp)
    success &= classification_success
    classification_invalid_success, _ = test_post_classification_with_invalid_model(args.device_id, timestamp)
    success &= classification_invalid_success
    
    # Test video endpoint
    video_success, _ = test_post_video(args.device_id, timestamp, args.video_file)
    success &= video_success
    
    # Add multiple test entries
    add_test_data(args.device_id, args.model_id, timestamp, args.num_entries)
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
