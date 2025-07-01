#!/usr/bin/env python3
"""Test that confidence arrays can accept any content type."""

import requests
import json
import sys
from datetime import datetime

API_URL = "http://localhost:8000"
API_KEY = "local-test-key"

def check_api_health():
    """Check if API is running"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✓ API is healthy")
            return True
    except:
        pass
    print("✗ API is not running. Start it with: python run_local.py")
    return False

def test_flexible_confidence_arrays():
    """Test that confidence arrays accept various data types."""
    base_data = {
        "device_id": "test-device-001",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model_id": "test-model-v1",
        "family": "Apidae",
        "genus": "Apis",
        "species": "mellifera",
        "family_confidence": 0.95,
        "genus_confidence": 0.92,
        "species_confidence": 0.88
    }
    
    # Test cases with different data types for confidence arrays
    test_cases = [
        {
            "name": "Arrays of numbers",
            "data": {
                **base_data,
                "family_confidence_array": [0.9, 0.05, 0.03, 0.02],
                "genus_confidence_array": [0.85, 0.1, 0.05],
                "species_confidence_array": [0.8, 0.15, 0.05]
            }
        },
        {
            "name": "Strings",
            "data": {
                **base_data,
                "family_confidence_array": "high confidence",
                "genus_confidence_array": "medium confidence",
                "species_confidence_array": "low confidence"
            }
        },
        {
            "name": "Numbers",
            "data": {
                **base_data,
                "family_confidence_array": 0.95,
                "genus_confidence_array": 0.85,
                "species_confidence_array": 0.75
            }
        },
        {
            "name": "Objects/Dictionaries",
            "data": {
                **base_data,
                "family_confidence_array": {"top_3": ["Apidae", "Vespidae", "Formicidae"], "scores": [0.9, 0.05, 0.05]},
                "genus_confidence_array": {"top_2": ["Apis", "Bombus"], "scores": [0.85, 0.15]},
                "species_confidence_array": {"candidates": ["mellifera", "cerana"], "probabilities": [0.8, 0.2]}
            }
        },
        {
            "name": "Mixed array types",
            "data": {
                **base_data,
                "family_confidence_array": [0.9, "high", {"rank": 1}],
                "genus_confidence_array": ["Apis", 0.85, True],
                "species_confidence_array": [{"name": "mellifera"}, 0.8, "confirmed"]
            }
        },
        {
            "name": "Null values",
            "data": {
                **base_data,
                "family_confidence_array": None,
                "genus_confidence_array": None,
                "species_confidence_array": None
            }
        },
        {
            "name": "Boolean values",
            "data": {
                **base_data,
                "family_confidence_array": True,
                "genus_confidence_array": False,
                "species_confidence_array": True
            }
        }
    ]
    
    print("Testing flexible confidence array types...")
    all_passed = True
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        response = requests.post(
            f"{API_URL}/classifications",
            headers={"x-api-key": API_KEY},
            json=test_case['data']
        )
        
        if response.status_code == 200:
            print(f"✓ {test_case['name']} - SUCCESS")
            result = response.json()
            stored_data = result.get('data', {})
            
            # Verify the values were stored
            for field in ['family_confidence_array', 'genus_confidence_array', 'species_confidence_array']:
                if field in test_case['data']:
                    if field in stored_data:
                        print(f"  - {field}: {stored_data[field]}")
                    else:
                        print(f"  - WARNING: {field} not in response")
        else:
            print(f"✗ {test_case['name']} - FAILED")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text}")
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    if not check_api_health():
        sys.exit(1)
    
    if test_flexible_confidence_arrays():
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)