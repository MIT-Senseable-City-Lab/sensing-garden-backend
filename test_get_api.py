#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

import requests

# Import the Sensing Garden client package
from sensing_garden_client import SensingGardenClient, get_models, get_detections, get_classifications
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

def test_get_endpoint(endpoint_type, device_id, model_id, timestamp=None, start_time=None, end_time=None):
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
            data = get_detections(
                client=client,
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10
            )
        elif endpoint_type == 'classification':
            data = get_classifications(
                client=client,
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10
            )
        else:  # model
            data = get_models(
                client=client,
                device_id=device_id,
                model_id=model_id,
                start_time=start_time,
                end_time=end_time,
                limit=10
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
            
            success = True
        else:
            print(f"⚠️ No {endpoint_type} items found")
            success = False
            
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

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API GET endpoints')
    parser.add_argument('--model', action='store_true', help='Test model API GET endpoint')
    parser.add_argument('--detection', action='store_true', help='Test detection API GET endpoint')
    parser.add_argument('--classification', action='store_true', help='Test classification API GET endpoint')
    parser.add_argument('--recent', action='store_true', help='Test for recent data (last 24h)')
    parser.add_argument('--verify', action='store_true', help='Verify test data exists')
    parser.add_argument('--hours', type=int, default=24, help='Hours to look back for recent test')
    parser.add_argument('--device', type=str, default="test-device", help='Device ID to use')
    parser.add_argument('--model-id', type=str, default="test-model-2025", help='Model ID to use')
    parser.add_argument('--timestamp', type=str, help='Specific timestamp to search for')
    args = parser.parse_args()
    
    # Set device and model IDs
    device_id = args.device
    model_id = args.model_id
    timestamp = args.timestamp
    
    # If no specific arguments provided, run all tests
    run_all = not (args.model or args.detection or args.classification or args.verify or args.recent)
    
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
    
    print("\nGET API Tests completed.")
