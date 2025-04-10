#!/usr/bin/env python3
"""
Tests for the Sensing Garden API classification endpoints.
This module tests both uploading and retrieving plant classifications.
"""
import argparse
import base64
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

import requests

from test_utils import (
    DEFAULT_TEST_DEVICE_ID,
    DEFAULT_TEST_MODEL_ID,
    get_client,
    create_test_image,
    generate_random_confidence,
    get_random_test_name,
    TEST_FAMILIES,
    TEST_GENERA,
    TEST_SPECIES,
    print_response
)

def test_add_classification(
    device_id: str,
    model_id: str,
    timestamp: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Test uploading a classification to the Sensing Garden API.
    
    Args:
        device_id: Device ID to use for testing
        model_id: Model ID to use for testing
        timestamp: Optional timestamp to use (defaults to current time)
        
    Returns:
        Tuple of (success, timestamp)
    """
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = timestamp or datetime.now().isoformat()
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting CLASSIFICATION UPLOAD with device_id: {device_id}, model_id: {model_id}")
    
    try:
        # Create test image
        image_data = create_test_image()
        
        # Generate random classification data
        family = get_random_test_name(TEST_FAMILIES)
        genus = get_random_test_name(TEST_GENERA)
        species = get_random_test_name(TEST_SPECIES)
        family_confidence = generate_random_confidence()
        genus_confidence = generate_random_confidence()
        species_confidence = generate_random_confidence()
        
        # Add the classification
        response_data = client.classifications.add(
            device_id=device_id,
            model_id=model_id,
            image_data=image_data,
            family=family,
            genus=genus,
            species=species,
            family_confidence=family_confidence,
            genus_confidence=genus_confidence,
            species_confidence=species_confidence,
            timestamp=request_timestamp
        )
        
        print_response(response_data)
        print(f"\n✅ Classification upload successful!")
        success = True
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Classification upload failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    
    return success, request_timestamp

def test_add_classification_with_invalid_model(
    device_id: str,
    timestamp: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Test uploading a classification with an invalid model ID.
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
    
    print(f"\n\nTesting CLASSIFICATION with invalid model_id: {invalid_model_id}")
    
    try:
        # Create test image
        image_data = create_test_image()
        
        # Generate random classification data
        family = get_random_test_name(TEST_FAMILIES)
        genus = get_random_test_name(TEST_GENERA)
        species = get_random_test_name(TEST_SPECIES)
        family_confidence = generate_random_confidence()
        genus_confidence = generate_random_confidence()
        species_confidence = generate_random_confidence()
        
        # Add the classification with invalid model ID
        response_data = client.classifications.add(
            device_id=device_id,
            model_id=invalid_model_id,
            image_data=image_data,
            family=family,
            genus=genus,
            species=species,
            family_confidence=family_confidence,
            genus_confidence=genus_confidence,
            species_confidence=species_confidence,
            timestamp=request_timestamp
        )
        
        # If we get here, the test failed because the request should have been rejected
        print(f"❌ Classification with invalid model_id was accepted unexpectedly!")
        print_response(response_data)
        return False, request_timestamp
            
    except requests.exceptions.RequestException as e:
        # This is the expected outcome - request should fail
        print(f"✅ Classification with invalid model_id failed as expected!")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return True, request_timestamp
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, request_timestamp

def test_fetch_classifications(
    device_id: str,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Test retrieving classifications from the Sensing Garden API.
    
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
    
    print(f"\n\nTesting CLASSIFICATION FETCH with device_id: {device_id}, model_id: {model_id}")
    print(f"Searching from {start_time} to {end_time}")
    
    try:
        # Use the classifications.fetch method to get classifications
        data = client.classifications.fetch(
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
            print(f"✅ Classification fetch successful! Found {len(data['items'])} classifications.")
            
            # Print details of each classification
            for i, classification in enumerate(data['items']):
                print(f"\nClassification {i+1}:")
                print(f"  Device ID: {classification.get('device_id')}")
                print(f"  Model ID: {classification.get('model_id')}")
                print(f"  Timestamp: {classification.get('timestamp')}")
                print(f"  Family: {classification.get('family')}")
                print(f"  Genus: {classification.get('genus')}")
                print(f"  Species: {classification.get('species')}")
                print(f"  Confidence: {classification.get('confidence')}")
                
                # Print image URL if available
                if 'image_url' in classification:
                    print(f"  Image URL: {classification.get('image_url')}")
                
                # Print metadata if available
                if 'metadata' in classification:
                    print(f"  Metadata: {classification.get('metadata')}")
            
            return True, data
        else:
            print(f"❌ No classifications found for device {device_id} in the specified time range.")
            return False, data
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Classification fetch request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return False, None
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, None

def add_test_classifications(
    device_id: str,
    model_id: str,
    num_classifications: int = 3
) -> bool:
    """
    Add test classifications for a device.
    
    Args:
        device_id: Device ID to use
        model_id: Model ID to use
        num_classifications: Number of classifications to add
        
    Returns:
        bool: Whether all classifications were added successfully
    """
    print(f"\nAdding {num_classifications} test classifications for device {device_id}")
    
    success = True
    for i in range(num_classifications):
        upload_success, _ = test_add_classification(
            device_id=device_id,
            model_id=model_id,
            timestamp=datetime.now().isoformat()
        )
        success = success and upload_success
    
    return success

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API classification endpoints')
    parser.add_argument('--device-id', type=str, default=DEFAULT_TEST_DEVICE_ID,
                      help=f'Device ID to use for testing (default: {DEFAULT_TEST_DEVICE_ID})')
    parser.add_argument('--model-id', type=str, default=DEFAULT_TEST_MODEL_ID,
                      help=f'Model ID to use for testing (default: {DEFAULT_TEST_MODEL_ID})')
    parser.add_argument('--timestamp', type=str, help='Optional timestamp to use for testing')
    parser.add_argument('--upload', action='store_true', help='Test classification upload')
    parser.add_argument('--fetch', action='store_true', help='Test classification fetch')
    parser.add_argument('--test-invalid', action='store_true', help='Test with invalid model ID')
    parser.add_argument('--add-test-data', action='store_true', help='Add test classifications')
    parser.add_argument('--num-classifications', type=int, default=3, help='Number of test classifications to add')
    
    args = parser.parse_args()
    
    # Use provided timestamp or generate a new one
    timestamp = args.timestamp or datetime.now().isoformat()
    
    # Run the appropriate tests
    success = True
    
    # Default to running both upload and fetch if neither is specified
    run_upload = args.upload or (not args.upload and not args.fetch)
    run_fetch = args.fetch or (not args.upload and not args.fetch)
    
    # Test classification upload
    if run_upload:
        upload_success, _ = test_add_classification(args.device_id, args.model_id, timestamp)
        success &= upload_success
    
    # Test with invalid model ID if requested
    if args.test_invalid:
        invalid_success, _ = test_add_classification_with_invalid_model(args.device_id, timestamp)
        success &= invalid_success
    
    # Add test data if requested
    if args.add_test_data:
        add_success = add_test_classifications(args.device_id, args.model_id, args.num_classifications)
        success &= add_success
    
    # Test classification fetch
    if run_fetch:
        fetch_success, _ = test_fetch_classifications(args.device_id, args.model_id)
        success &= fetch_success
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
