#!/usr/bin/env python3
"""
Test script for the new confidence array fields in classifications API.
Run this after starting the local environment to verify the implementation.
"""

import requests
import json
import base64
from datetime import datetime, timezone

# Local API endpoint
API_URL = "http://localhost:8000"
API_KEY = "local-test-key"

def create_test_image():
    """Create a simple test image (1x1 white pixel)"""
    # PNG header for 1x1 white image
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd4l\x00\x00\x00\x00IEND\xaeB`\x82'
    return base64.b64encode(png_data).decode('utf-8')

def test_classification_with_arrays():
    """Test creating a classification with confidence arrays"""
    
    # Prepare test data
    classification_data = {
        "device_id": "test-device-001",
        "model_id": "test-model-v1",
        "track_id": "test-track-123",
        "image": create_test_image(),
        "family": "Lepidoptera",
        "genus": "Vanessa",
        "species": "Vanessa cardui",
        "family_confidence": 0.95,
        "genus_confidence": 0.87,
        "species_confidence": 0.73,
        # New array fields - probability distributions
        "family_confidence_array": [0.95, 0.03, 0.01, 0.01],  # 4 possible families
        "genus_confidence_array": [0.87, 0.08, 0.03, 0.02],   # 4 possible genera
        "species_confidence_array": [0.73, 0.15, 0.07, 0.05]   # 4 possible species
    }
    
    print("Testing classification with confidence arrays...")
    print(f"Sending POST request to {API_URL}/classifications")
    
    # Send POST request
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    response = requests.post(
        f"{API_URL}/classifications",
        headers=headers,
        json=classification_data
    )
    
    print(f"\nResponse status: {response.status_code}")
    print(f"Response body: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code != 200:
        print("\n❌ Failed to create classification")
        return False
    
    print("\n✓ Successfully created classification with confidence arrays")
    
    # Now retrieve the classification to verify arrays are stored
    print("\nRetrieving classifications to verify arrays...")
    
    get_response = requests.get(
        f"{API_URL}/classifications",
        headers=headers,
        params={"device_id": "test-device-001", "limit": 1}
    )
    
    if get_response.status_code == 200:
        data = get_response.json()
        if data.get('items') and len(data['items']) > 0:
            item = data['items'][0]
            print("\nRetrieved classification:")
            print(f"  Track ID: {item.get('track_id')}")
            print(f"  Species: {item.get('species')}")
            print(f"  Species confidence: {item.get('species_confidence')}")
            
            # Check for array fields
            if 'family_confidence_array' in item:
                print(f"  ✓ Family confidence array: {item['family_confidence_array']}")
            else:
                print("  ⚠️  Family confidence array not found")
                
            if 'genus_confidence_array' in item:
                print(f"  ✓ Genus confidence array: {item['genus_confidence_array']}")
            else:
                print("  ⚠️  Genus confidence array not found")
                
            if 'species_confidence_array' in item:
                print(f"  ✓ Species confidence array: {item['species_confidence_array']}")
            else:
                print("  ⚠️  Species confidence array not found")
            
            return all(key in item for key in ['family_confidence_array', 'genus_confidence_array', 'species_confidence_array'])
    
    return False

def test_backward_compatibility():
    """Test that classifications without arrays still work"""
    
    print("\n\nTesting backward compatibility (no arrays)...")
    
    # Classification without array fields
    classification_data = {
        "device_id": "test-device-001",
        "model_id": "test-model-v1",
        "image": create_test_image(),
        "family": "Coleoptera",
        "genus": "Coccinella",
        "species": "Coccinella septempunctata",
        "family_confidence": 0.92,
        "genus_confidence": 0.88,
        "species_confidence": 0.81
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    response = requests.post(
        f"{API_URL}/classifications",
        headers=headers,
        json=classification_data
    )
    
    print(f"\nResponse status: {response.status_code}")
    
    if response.status_code == 200:
        print("✓ Backward compatibility maintained - classifications without arrays still work")
        return True
    else:
        print("❌ Backward compatibility broken")
        print(f"Response: {response.json()}")
        return False

def main():
    """Run all tests"""
    print("=== Testing Confidence Array Implementation ===\n")
    
    # Check if API is running
    try:
        health = requests.get(f"{API_URL}/health")
        if health.status_code != 200:
            print("❌ API server not running. Please start it with 'make start-local'")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server at http://localhost:8000")
        print("Please start the local environment with 'make start-local'")
        return
    
    # Run tests
    test1_passed = test_classification_with_arrays()
    test2_passed = test_backward_compatibility()
    
    print("\n\n=== Test Summary ===")
    print(f"Classification with arrays: {'✓ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Backward compatibility: {'✓ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n✅ All tests passed! The confidence array implementation is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the implementation.")

if __name__ == '__main__':
    main()