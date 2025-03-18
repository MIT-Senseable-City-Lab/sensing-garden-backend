#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime
import uuid

# API configuration
API_KEY = os.environ.get("SENSING_GARDEN_API_KEY", "gMVUsSGzdZ5JgLgpadHtA9yd3Jz5THYs2pEPP7Al")
API_BASE = "https://80tryunqte.execute-api.us-east-1.amazonaws.com"

def test_models_api():
    # Generate a unique model ID
    model_id = f"test-model-{uuid.uuid4().hex[:8]}"
    device_id = "test-device-123"
    
    # Create test model data
    model_data = {
        'device_id': device_id,
        'model_id': model_id,
        'timestamp': datetime.utcnow().isoformat(),
        'name': 'Test Model API',
        'description': 'A test model for API testing',
        'version': '1.0',
        'metadata': {
            'type': 'test'
        }
    }
    
    print(f"Testing with model ID: {model_id}")
    
    # Test POST /models
    try:
        print("\n1. Testing POST /models...")
        response = requests.post(
            f"{API_BASE}/models",
            json=model_data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY
            }
        )
        print(f"Status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response: {response.text}")
        response.raise_for_status()
        print("✅ POST /models test passed")
    except Exception as e:
        print(f"❌ POST /models test failed: {str(e)}")
    
    # Test GET /models
    try:
        print("\n2. Testing GET /models...")
        response = requests.get(
            f"{API_BASE}/models",
            params={"device_id": device_id, "model_id": model_id},
            headers={"x-api-key": API_KEY}
        )
        print(f"Status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response: {response.text}")
        response.raise_for_status()
        print("✅ GET /models test passed")
    except Exception as e:
        print(f"❌ GET /models test failed: {str(e)}")

if __name__ == "__main__":
    test_models_api()
