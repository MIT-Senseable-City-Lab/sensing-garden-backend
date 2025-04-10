#!/usr/bin/env python3
"""
Tests for the Sensing Garden API model endpoints.
This module tests both uploading and retrieving ML models.
"""
import argparse
import sys
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

import requests

from test_utils import (
    DEFAULT_TEST_DEVICE_ID,
    DEFAULT_TEST_MODEL_ID,
    get_client,
    generate_random_string,
    print_response
)

def test_create_model(
    model_id: Optional[str] = None,
    timestamp: Optional[str] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Test uploading a model to the Sensing Garden API.
    
    Args:
        model_id: Optional model ID to use (generates a new one if not provided)
        timestamp: Optional timestamp to use (defaults to current time)
        
    Returns:
        Tuple of (success, model_id, timestamp)
    """
    # Create a unique model ID if not provided
    model_id = model_id or f"test-model-{generate_random_string(8)}"
    
    # Create a unique timestamp for this request
    request_timestamp = timestamp or datetime.now().isoformat()
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting MODEL UPLOAD with model_id: {model_id}")
    
    try:
        # Create the model
        response_data = client.models.create(
            model_id=model_id,
            name=f"Test Model {model_id}",
            version="1.0.0",
            description=f"Test model created at {request_timestamp}",
            timestamp=request_timestamp
        )
        
        print_response(response_data)
        print(f"\n✅ Model creation successful!")
        success = True
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Model upload failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    
    return success, model_id, request_timestamp

def test_fetch_models(
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Test retrieving models from the Sensing Garden API.
    
    Args:
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
    
    print(f"\n\nTesting MODEL FETCH" + (f" with model_id: {model_id}" if model_id else ""))
    print(f"Searching from {start_time} to {end_time}")
    
    try:
        # Use the models.fetch method to get models
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
            print(f"✅ Model fetch successful! Found {len(data['items'])} models.")
            
            # Print details of each model
            for i, model in enumerate(data['items']):
                print(f"\nModel {i+1}:")
                print(f"  Model ID: {model.get('model_id')}")
                print(f"  Name: {model.get('name')}")
                print(f"  Version: {model.get('version')}")
                print(f"  Description: {model.get('description')}")
                print(f"  Type: {model.get('model_type')}")
                print(f"  Framework: {model.get('framework')}")
                print(f"  Timestamp: {model.get('timestamp')}")
                
                # Print metadata if available
                if 'metadata' in model:
                    print(f"  Metadata: {model.get('metadata')}")
            
            return True, data
        else:
            print(f"❌ No models found in the specified time range.")
            return False, data
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Model fetch request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return False, None
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, None

def add_test_models(num_models: int = 3) -> List[str]:
    """
    Add test models.
    
    Args:
        num_models: Number of models to add
        
    Returns:
        List of created model IDs
    """
    print(f"\nAdding {num_models} test models")
    
    model_ids = []
    for i in range(num_models):
        success, model_id, _ = test_create_model()
        if success:
            model_ids.append(model_id)
    
    return model_ids

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API model endpoints')
    parser.add_argument('--model-id', type=str, default=DEFAULT_TEST_MODEL_ID,
                      help=f'Model ID to use for testing (default: {DEFAULT_TEST_MODEL_ID})')
    parser.add_argument('--timestamp', type=str, help='Optional timestamp to use for testing')
    parser.add_argument('--upload', action='store_true', help='Test model creation')
    parser.add_argument('--fetch', action='store_true', help='Test model fetch')
    parser.add_argument('--add-test-data', action='store_true', help='Add test models')
    parser.add_argument('--num-models', type=int, default=3, help='Number of test models to add')
    
    args = parser.parse_args()
    
    # Use provided timestamp or generate a new one
    timestamp = args.timestamp or datetime.now().isoformat()
    
    # Run the appropriate tests
    success = True
    
    # Default to running both upload and fetch if neither is specified
    run_upload = args.upload or (not args.upload and not args.fetch)
    run_fetch = args.fetch or (not args.upload and not args.fetch)
    
    # Test model creation
    if run_upload:
        upload_success, model_id, _ = test_create_model(args.model_id, timestamp)
        success &= upload_success
    
    # Add test data if requested
    if args.add_test_data:
        model_ids = add_test_models(args.num_models)
        success &= len(model_ids) == args.num_models
    
    # Test model fetch
    if run_fetch:
        fetch_success, _ = test_fetch_models(args.model_id)
        success &= fetch_success
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
