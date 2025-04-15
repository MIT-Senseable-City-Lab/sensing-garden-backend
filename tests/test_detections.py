#!/usr/bin/env python3
"""
Tests for the Sensing Garden API detection endpoints.
This module tests both uploading and retrieving object detections.
"""
import argparse
import base64
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

import requests

from .test_utils import (
    get_client,
    create_test_image,
    generate_random_confidence,
    generate_random_bounding_box,
    print_response
)

def test_add_detection(
    device_id,
    model_id,
    timestamp=None,
    num_detections=3
) -> Tuple[bool, Optional[str]]:
    """
    Test uploading a detection to the Sensing Garden API.
    
    Args:
        device_id: Device ID to use for testing
        model_id: Model ID to use for testing
        timestamp: Optional timestamp to use (defaults to current time)
        num_detections: Number of random detections to include
        
    Returns:
        Tuple of (success, timestamp)
    """
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = timestamp or datetime.now().isoformat()
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting DETECTION UPLOAD with device_id: {device_id}, model_id: {model_id}")
    
    try:
        # Create test image
        image_data = create_test_image()
        
        # Generate a random bounding box
        bounding_box = generate_random_bounding_box()
        
        # Add the detection
        response_data = client.detections.add(
            device_id=device_id,
            model_id=model_id,
            image_data=image_data,
            bounding_box=bounding_box,
            timestamp=request_timestamp
        )
        
        print_response(response_data)
        print(f"\n✅ Detection upload successful!")
        success = True
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Detection upload failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    
    assert success, f"Detection test failed at {request_timestamp}"

def test_add_detection_with_invalid_model(
    device_id,
    nonexistent_model_id,
    timestamp=None,
    num_detections=3
) -> Tuple[bool, Optional[str]]:
    """
    Test uploading a detection with an invalid model ID.
    This should fail with an appropriate error message.
    
    Args:
        device_id: Device ID to use for testing
        timestamp: Optional timestamp to use (defaults to current time)
        
    Returns:
        Tuple of (success, timestamp)
    """
    # Create a unique timestamp for this request
    request_timestamp = timestamp or datetime.now().isoformat()
    
    # Generate a random invalid model ID
    invalid_model_id = str(uuid.uuid4())
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting DETECTION with invalid model_id: {invalid_model_id}")
    
    try:
        # Create test image
        image_data = create_test_image()
        
        # Generate a random bounding box
        bounding_box = generate_random_bounding_box()
        
        # Add the detection with invalid model ID
        response_data = client.detections.add(
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            bounding_box=bounding_box,
            timestamp=request_timestamp
        )
        
        # If we get here, the test failed because the request should have been rejected
        print(f"❌ Detection with invalid model_id was accepted unexpectedly!")
        print_response(response_data)
        return False, request_timestamp
            
    except requests.exceptions.RequestException as e:
        # This is the expected outcome - request should fail
        print(f"✅ Detection with invalid model_id failed as expected!")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return True, request_timestamp
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, request_timestamp

def test_fetch_detections(
    device_id: str,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Test retrieving detections from the Sensing Garden API.
    
    Args:
        device_id: Device ID to filter by
        model_id: Optional model ID to filter by
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        sort_by: Optional attribute to sort by
        sort_desc: Whether to sort in descending order
        
    Returns:
        Tuple of (success, response data)
    """
    if not start_time:
        # If no specific start_time provided, use a time range from beginning of 2023
        start_time = datetime(2023, 1, 1).isoformat()
    
    if not end_time:
        # If no specific end_time provided, use current time
        end_time = datetime.now().isoformat()
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting DETECTION FETCH with device_id: {device_id}, model_id: {model_id}")
    print(f"Searching from {start_time} to {end_time}")
    
    try:
        # Use the detections.fetch method to get detections
        data = client.detections.fetch(
            device_id=device_id,
            model_id=model_id,
            start_time=start_time,
            end_time=end_time,
            limit=10,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        # Check if we got any results
        if data.get('items') and len(data['items']) > 0:
            print(f"✅ Detection fetch successful! Found {len(data['items'])} detections.")
            
            # Print details of each detection
            for i, detection in enumerate(data['items']):
                print(f"\nDetection {i+1}:")
                print(f"  Device ID: {detection.get('device_id')}")
                print(f"  Model ID: {detection.get('model_id')}")
                print(f"  Timestamp: {detection.get('timestamp')}")
                
                # Print detection results
                if 'detections' in detection:
                    print(f"  Number of objects detected: {len(detection['detections'])}")
                    for j, obj in enumerate(detection['detections']):
                        print(f"    Object {j+1}: {obj.get('label')} (confidence: {obj.get('confidence'):.2f})")
                
                # Print image URL if available
                if 'image_url' in detection:
                    print(f"  Image URL: {detection.get('image_url')}")
                
                # Print metadata if available
                if 'metadata' in detection:
                    print(f"  Metadata: {detection.get('metadata')}")
            
            return True, data
        else:
            print(f"❌ No detections found for device {device_id} in the specified time range.")
            return False, data
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Detection fetch request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return False, None
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, None

def add_test_detections(
    device_id: str,
    model_id: str,
    num_detections: int = 3
) -> bool:
    """
    Add test detections for a device.
    
    Args:
        device_id: Device ID to use
        model_id: Model ID to use
        num_detections: Number of detections to add
        
    Returns:
        bool: Whether all detections were added successfully
    """
    print(f"\nAdding {num_detections} test detections for device {device_id}")
    
    success = True
    for i in range(num_detections):
        upload_success, _ = test_add_detection(
            device_id=device_id,
            model_id=model_id,
            timestamp=datetime.now().isoformat()
        )
        success = success and upload_success
    
    return success

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API detection endpoints')
    parser.add_argument('--device-id', type=str, default=DEFAULT_TEST_DEVICE_ID,
                      help=f'Device ID to use for testing (default: {DEFAULT_TEST_DEVICE_ID})')
    parser.add_argument('--model-id', type=str, default=DEFAULT_TEST_MODEL_ID,
                      help=f'Model ID to use for testing (default: {DEFAULT_TEST_MODEL_ID})')
    parser.add_argument('--timestamp', type=str, help='Optional timestamp to use for testing')
    parser.add_argument('--upload', action='store_true', help='Test detection upload')
    parser.add_argument('--fetch', action='store_true', help='Test detection fetch')
    parser.add_argument('--test-invalid', action='store_true', help='Test with invalid model ID')
    parser.add_argument('--add-test-data', action='store_true', help='Add test detections')
    parser.add_argument('--num-detections', type=int, default=3, help='Number of test detections to add')
    
    args = parser.parse_args()
    
    # Use provided timestamp or generate a new one
    timestamp = args.timestamp or datetime.now().isoformat()
    
    # Run the appropriate tests
    success = True
    
    # Default to running both upload and fetch if neither is specified
    run_upload = args.upload or (not args.upload and not args.fetch)
    run_fetch = args.fetch or (not args.upload and not args.fetch)
    
    # Test detection upload
    if run_upload:
        upload_success, _ = test_add_detection(args.device_id, args.model_id, timestamp)
        success &= upload_success
    
    # Test with invalid model ID if requested
    if args.test_invalid:
        invalid_success, _ = test_add_detection_with_invalid_model(args.device_id, timestamp)
        success &= invalid_success
    
    # Add test data if requested
    if args.add_test_data:
        add_success = add_test_detections(args.device_id, args.model_id, args.num_detections)
        success &= add_success
    
    # Test detection fetch
    if run_fetch:
        fetch_success, _ = test_fetch_detections(args.device_id, args.model_id)
        success &= fetch_success
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
