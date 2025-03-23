#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

import requests

# Import the Sensing Garden client package
from sensing_garden_client import SensingGardenClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add lambda/src to the Python path so we can import the schema
sys.path.append(os.path.join(os.path.dirname(__file__), 'lambda/src'))

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# The endpoint modules handle their own configuration via environment variables

def test_get_endpoint(endpoint_type, device_id, model_id, timestamp=None, start_time=None, end_time=None, sort_by=None, sort_desc=False):
    """Test a GET API endpoint (detection, classification, or model) using the sensing_garden_api package"""
    if not timestamp and not start_time:
        # If no specific timestamp provided, use a time range
        start_time = datetime(2023, 1, 1).isoformat()
        end_time = datetime.now().isoformat()
    elif timestamp and not start_time:
        # If timestamp provided, set narrow time range around it
        from datetime import timedelta
        timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00') if timestamp.endswith('Z') else timestamp)
        start_time = (timestamp_dt - timedelta(minutes=1)).isoformat()
        end_time = (timestamp_dt + timedelta(minutes=1)).isoformat()
    
    # Initialize the client with API base URL from environment
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url)
    
    print(f"\n\nTesting {endpoint_type.upper()} GET with device_id: {device_id}, model_id: {model_id}")
    if timestamp:
        print(f"Searching for timestamp: {timestamp}")
    else:
        print(f"Searching from {start_time} to {end_time}")
    
    try:
        # Use the appropriate read endpoint function from sensing_garden_api
        if endpoint_type == 'detection':
            data = client.detections.fetch(
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
        elif endpoint_type == 'classification':
            data = client.classifications.fetch(
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
        else:  # model
            data = client.models.fetch(
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
        
        # Check if we got any results
        if data.get('items') and len(data['items']) > 0:
            print(f"✅ {endpoint_type.capitalize()} GET successful! Found {len(data['items'])} items.")
            
            # If timestamp is provided, try to find exact match
            if timestamp:
                item = next((item for item in data['items'] if item.get('timestamp') == timestamp), None)
                if item:
                    print(f"✅ Found exact match for timestamp {timestamp}")
                    print(f"Item details: {json.dumps(item, indent=2, cls=DecimalEncoder)}")
                else:
                    print(f"ℹ️ No exact match for timestamp {timestamp}, but found other items")
            
            # Show a sample of results
            print(f"\nSample of first result:")
            print(json.dumps(data['items'][0], indent=2, cls=DecimalEncoder))
            
            # Check for pagination
            if data.get('next_token'):
                print(f"⚠️ More results available. Use next_token: {data['next_token']}")
            
            # Additional verification for detection responses
            if endpoint_type == 'detection':
                first_item = data['items'][0]
                if 'bounding_box' not in first_item:
                    print("❌ Warning: bounding_box field is missing from detection response")
                else:
                    print(f"✅ bounding_box field present: {first_item['bounding_box']}")
            
            success = True
        else:
            print(f"⚠️ No {endpoint_type} items found")
            success = False
            
    except ValueError as e:
        print(f"✅ {endpoint_type.capitalize()} API GET request failed: {str(e)}")
        raise  # Re-raise ValueError to be caught by tests
    except requests.exceptions.RequestException as e:
        print(f"❌ {endpoint_type.capitalize()} API GET request failed: {str(e)}")
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

def test_get_detection(device_id, model_id, timestamp=None):
    """Test the detection API GET endpoint"""
    return test_get_endpoint('detection', device_id, model_id, timestamp)

def test_get_classification(device_id, model_id, timestamp=None):
    """Test the classification API GET endpoint"""
    return test_get_endpoint('classification', device_id, model_id, timestamp)

def test_get_model(device_id, model_id):
    """Test the model API GET endpoint"""
    return test_get_endpoint('model', device_id, model_id)

def verify_data_exists(device_id, model_id):
    """Verify that test data exists for the specified device/model"""
    detection_exists = test_get_detection(device_id, model_id)
    classification_exists = test_get_classification(device_id, model_id)
    model_exists = test_get_model(device_id, model_id)
    
    if detection_exists or classification_exists or model_exists:
        print("\n✅ Test data exists for this device/model")
        if not detection_exists:
            print("⚠️ No detection data found")
        if not classification_exists:
            print("⚠️ No classification data found")
        if not model_exists:
            print("⚠️ No model data found")
    else:
        print("\n❌ No test data found for this device/model")
        print("You may want to run test_post_api.py first to create test data")
    
    return detection_exists or classification_exists or model_exists

def test_recent_data(device_id, model_id, hours=24):
    """Test for recent data within the last specified hours"""
    from datetime import datetime, timedelta
    
    end_time = datetime.now().isoformat()
    start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    print(f"\nChecking for data in the last {hours} hours...")
    print(f"Time range: {start_time} to {end_time}")
    
    detection_success = test_get_endpoint('detection', device_id, model_id, 
                                         start_time=start_time, end_time=end_time)
    classification_success = test_get_endpoint('classification', device_id, model_id, 
                                              start_time=start_time, end_time=end_time)
    
    if detection_success or classification_success:
        print(f"\n✅ Recent data found within the last {hours} hours")
    else:
        print(f"\n⚠️ No recent data found within the last {hours} hours")


def test_sorting(endpoint_type, device_id, model_id, sort_by='timestamp'):
    """Test the sorting functionality for the specified endpoint"""
    # Initialize the client with API base URL from environment
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url)
    
    print(f"\n\nTesting {endpoint_type.upper()} GET with sorting by '{sort_by}'")
    print(f"Device ID: {device_id}, Model ID: {model_id}")
    
    # We'll use a wide date range to ensure we get results
    start_time = datetime(2023, 1, 1).isoformat()
    end_time = datetime.now().isoformat()
    
    try:
        # Get results with ascending sort
        if endpoint_type == 'detection':
            asc_data = client.detections.fetch(
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=False
            )
        elif endpoint_type == 'classification':
            asc_data = client.classifications.fetch(
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=False
            )
        else:  # model
            asc_data = client.models.fetch(
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=False
            )
        
        # Get results with descending sort
        if endpoint_type == 'detection':
            desc_data = client.detections.fetch(
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=True
            )
        elif endpoint_type == 'classification':
            desc_data = client.classifications.fetch(
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=True
            )
        else:  # model
            desc_data = client.models.fetch(
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10,
                sort_by=sort_by,
                sort_desc=True
            )
        
        # Check if we got any results
        asc_items = asc_data.get('items', [])
        desc_items = desc_data.get('items', [])
        
        if not asc_items or not desc_items:
            print(f"⚠️ Not enough {endpoint_type} items found to test sorting")
            return False
        
        print(f"✅ Retrieved {len(asc_items)} items with ascending sort and {len(desc_items)} with descending sort")
        
        # Check the sorting is correct
        if len(asc_items) > 1 and len(desc_items) > 1:
            # Extract values from first and last items for each sort order
            asc_first_value = asc_items[0].get(sort_by)
            asc_last_value = asc_items[-1].get(sort_by)
            desc_first_value = desc_items[0].get(sort_by)
            desc_last_value = desc_items[-1].get(sort_by)
            
            print(f"\nAscending order - First: {asc_first_value}, Last: {asc_last_value}")
            print(f"Descending order - First: {desc_first_value}, Last: {desc_last_value}")
            
            # Verify correct sorting - ascending should go from low to high
            sorting_correct = True
            if asc_first_value and asc_last_value and asc_first_value > asc_last_value:
                print(f"❌ Ascending sort is incorrect: first value > last value")
                sorting_correct = False
            
            # Descending should go from high to low
            if desc_first_value and desc_last_value and desc_first_value < desc_last_value:
                print(f"❌ Descending sort is incorrect: first value < last value")
                sorting_correct = False
            
            # The first item of descending should match last item of ascending (roughly)
            if asc_last_value and desc_first_value and not (desc_first_value >= asc_last_value):
                print(f"⚠️ Last ascending item should be <= first descending item")
            
            if sorting_correct:
                print(f"✅ Sorting verification passed for {sort_by}!")
            return sorting_correct
        else:
            print(f"⚠️ Not enough items to verify sorting order properly")
            return True  # Still return True as the API didn't fail
            
    except requests.exceptions.RequestException as e:
        print(f"❌ {endpoint_type.capitalize()} API GET request with sorting failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return False
    except Exception as e:
        print(f"❌ Error in sorting test: {str(e)}")
        return False

def test_sorting_with_invalid_sort_desc(device_id, model_id):
    """Test that passing a non-boolean value for sort_desc raises an error"""
    try:
        test_get_endpoint('detection', device_id, model_id, sort_by='timestamp', sort_desc='true')
        assert False, "Expected ValueError was not raised"
    except ValueError as e:
        assert str(e) == "sort_desc must be a boolean value"
        print(f"✅ Correct error raised for invalid sort_desc value")
    except Exception as e:
        print(f"❌ Unexpected error type: {type(e)}")
        print(f"Error message: {str(e)}")
        assert False, "Expected ValueError but got different error type"

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API GET endpoints')
    parser.add_argument('--model', action='store_true', help='Test model API GET endpoint')
    parser.add_argument('--detection', action='store_true', help='Test detection API GET endpoint')
    parser.add_argument('--classification', action='store_true', help='Test classification API GET endpoint')
    parser.add_argument('--recent', action='store_true', help='Test recent data')
    parser.add_argument('--verify', action='store_true', help='Verify test data exists')
    parser.add_argument('--test-sort', action='store_true', help='Test sorting functionality')
    parser.add_argument('--test-invalid-sort', action='store_true', help='Test invalid sort_desc parameter')
    parser.add_argument('--sort-by', type=str, help='Attribute to sort by')
    parser.add_argument('--hours', type=int, default=24, help='Number of hours to check for recent data')
    parser.add_argument('--device', type=str, default='test-device', help='Device ID to test')
    parser.add_argument('--model-id', type=str, default='test-model-2025', help='Model ID to test')
    parser.add_argument('--timestamp', type=str, help='Specific timestamp to test')
    
    args = parser.parse_args()
    
    # Set device and model IDs
    device_id = args.device
    model_id = args.model_id
    timestamp = args.timestamp
    
    # If no specific arguments provided, run all tests
    run_all = not (args.model or args.detection or args.classification or args.verify or args.recent or args.test_sort or args.test_invalid_sort)
    
    # Test model API if requested
    if args.model or run_all:
        print("\nTesting model API GET endpoint...")
        test_get_model(device_id, model_id)
    
    # Test detection API if requested
    if args.detection or run_all:
        print("\nTesting detection API GET endpoint...")
        test_get_detection(device_id, model_id, timestamp)
    
    # Test classification API if requested
    if args.classification or run_all:
        print("\nTesting classification API GET endpoint...")
        test_get_classification(device_id, model_id, timestamp)
    
    # Verify test data exists if requested
    if args.verify or run_all:
        print("\nVerifying test data exists...")
        verify_data_exists(device_id, model_id)
    
    # Test for recent data if requested
    if args.recent or run_all:
        test_recent_data(device_id, model_id, args.hours)
        
    # Test sorting functionality if requested
    if args.test_sort or run_all:
        print("\n\n==== Testing Sorting Functionality ====\n")
        test_sorting('detection', device_id, model_id, args.sort_by)
        test_sorting('classification', device_id, model_id, args.sort_by)
        test_sorting('model', device_id, model_id, args.sort_by)
    
    # Test invalid sort_desc parameter if requested
    if args.test_invalid_sort or run_all:
        test_sorting_with_invalid_sort_desc(device_id, model_id)
    
    print("\nGET API Tests completed.")
