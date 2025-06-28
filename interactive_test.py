#!/usr/bin/env python3
"""
Interactive test script for the local environment.
Provides a menu-driven interface to test different features.
"""

import requests
import json
import base64
from datetime import datetime, timezone
import sys
import time

API_URL = "http://localhost:8000"
API_KEY = "local-test-key"

def create_test_image():
    """Create a simple test image"""
    # 1x1 white PNG
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd4l\x00\x00\x00\x00IEND\xaeB`\x82'
    return base64.b64encode(png_data).decode('utf-8')

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

def list_devices():
    """List all devices"""
    response = requests.get(f"{API_URL}/devices")
    if response.status_code == 200:
        devices = response.json().get('items', [])
        if devices:
            print(f"\nFound {len(devices)} device(s):")
            for device in devices:
                print(f"  - {device['device_id']} (created: {device.get('created', 'unknown')})")
        else:
            print("\nNo devices found")
    else:
        print(f"Error: {response.status_code}")

def create_device():
    """Create a new device"""
    device_id = input("Enter device ID (e.g., garden-pi-001): ").strip()
    if not device_id:
        print("Device ID required")
        return
    
    data = {"device_id": device_id}
    response = requests.post(f"{API_URL}/devices", 
                           headers={"Content-Type": "application/json"},
                           json=data)
    
    if response.status_code == 200:
        print(f"✓ Device '{device_id}' created successfully")
    else:
        print(f"Error: {response.json()}")

def create_detection():
    """Create a detection"""
    device_id = input("Enter device ID: ").strip()
    if not device_id:
        print("Device ID required")
        return
    
    data = {
        "device_id": device_id,
        "model_id": "yolov8-test",
        "image": create_test_image(),
        "confidence": 0.89,
        "object_class": "butterfly",
        "bounding_box": [10, 20, 100, 150]
    }
    
    response = requests.post(f"{API_URL}/detections",
                           headers={"Content-Type": "application/json"},
                           json=data)
    
    if response.status_code == 200:
        print("✓ Detection created successfully")
    else:
        print(f"Error: {response.json()}")

def create_classification_with_arrays():
    """Create a classification with confidence arrays"""
    device_id = input("Enter device ID: ").strip()
    if not device_id:
        print("Device ID required")
        return
    
    print("\nCreating classification with confidence arrays...")
    
    data = {
        "device_id": device_id,
        "model_id": "insect-classifier-v2",
        "track_id": f"track-{int(time.time())}",
        "image": create_test_image(),
        "family": "Lepidoptera",
        "genus": "Vanessa",
        "species": "Vanessa cardui",
        "family_confidence": 0.95,
        "genus_confidence": 0.87,
        "species_confidence": 0.73,
        "family_confidence_array": [0.95, 0.03, 0.01, 0.01],
        "genus_confidence_array": [0.87, 0.08, 0.03, 0.02],
        "species_confidence_array": [0.73, 0.15, 0.07, 0.05]
    }
    
    response = requests.post(f"{API_URL}/classifications",
                           headers={"Content-Type": "application/json"},
                           json=data)
    
    if response.status_code == 200:
        print("✓ Classification created successfully with arrays")
        print(f"  Track ID: {data['track_id']}")
    else:
        print(f"Error: {response.json()}")

def query_data():
    """Query detections and classifications"""
    device_id = input("Enter device ID (or press Enter for all): ").strip()
    
    params = {}
    if device_id:
        params['device_id'] = device_id
    
    print("\nDetections:")
    det_response = requests.get(f"{API_URL}/detections", params=params)
    if det_response.status_code == 200:
        detections = det_response.json().get('items', [])
        print(f"  Found {len(detections)} detection(s)")
        for det in detections[:3]:  # Show first 3
            print(f"    - {det['timestamp']}: {det['object_class']} (conf: {det['confidence']})")
    
    print("\nClassifications:")
    class_response = requests.get(f"{API_URL}/classifications", params=params)
    if class_response.status_code == 200:
        classifications = class_response.json().get('items', [])
        print(f"  Found {len(classifications)} classification(s)")
        for cls in classifications[:3]:  # Show first 3
            print(f"    - {cls['timestamp']}: {cls['species']}")
            if 'family_confidence_array' in cls:
                print(f"      ✓ Has confidence arrays")

def test_complete_workflow():
    """Test a complete workflow"""
    print("\n=== Testing Complete Workflow ===")
    
    # Create unique device
    device_id = f"workflow-test-{int(time.time())}"
    print(f"1. Creating device: {device_id}")
    
    response = requests.post(f"{API_URL}/devices", 
                           headers={"Content-Type": "application/json"},
                           json={"device_id": device_id})
    if response.status_code != 200:
        print("Failed to create device")
        return
    print("   ✓ Device created")
    
    # Create detection
    print("2. Creating detection...")
    det_data = {
        "device_id": device_id,
        "model_id": "yolov8-test",
        "image": create_test_image(),
        "confidence": 0.92,
        "object_class": "monarch_butterfly"
    }
    response = requests.post(f"{API_URL}/detections",
                           headers={"Content-Type": "application/json"},
                           json=det_data)
    if response.status_code != 200:
        print("Failed to create detection")
        return
    print("   ✓ Detection created")
    
    # Create classification with arrays
    print("3. Creating classification with arrays...")
    class_data = {
        "device_id": device_id,
        "model_id": "classifier-v2",
        "track_id": "workflow-track-123",
        "image": create_test_image(),
        "family": "Nymphalidae",
        "genus": "Danaus",
        "species": "Danaus plexippus",
        "family_confidence": 0.98,
        "genus_confidence": 0.95,
        "species_confidence": 0.91,
        "family_confidence_array": [0.98, 0.01, 0.01],
        "genus_confidence_array": [0.95, 0.03, 0.02],
        "species_confidence_array": [0.91, 0.06, 0.03]
    }
    response = requests.post(f"{API_URL}/classifications",
                           headers={"Content-Type": "application/json"},
                           json=class_data)
    if response.status_code != 200:
        print("Failed to create classification")
        return
    print("   ✓ Classification created")
    
    # Query data
    print("4. Querying data...")
    response = requests.get(f"{API_URL}/detections/count", 
                          params={"device_id": device_id})
    det_count = response.json().get('count', 0)
    
    response = requests.get(f"{API_URL}/classifications/count", 
                          params={"device_id": device_id})
    class_count = response.json().get('count', 0)
    
    print(f"   ✓ Found {det_count} detection(s), {class_count} classification(s)")
    
    # Verify arrays
    print("5. Verifying confidence arrays...")
    response = requests.get(f"{API_URL}/classifications", 
                          params={"device_id": device_id})
    if response.status_code == 200:
        items = response.json().get('items', [])
        if items and 'species_confidence_array' in items[0]:
            print("   ✓ Confidence arrays stored correctly")
            print(f"     Species array: {items[0]['species_confidence_array']}")
        else:
            print("   ✗ Confidence arrays not found")
    
    print("\n✅ Workflow test completed successfully!")

def main():
    """Main interactive menu"""
    print("=== Sensing Garden Local Test Interface ===")
    
    if not check_api_health():
        return
    
    while True:
        print("\n--- Menu ---")
        print("1. List devices")
        print("2. Create device")
        print("3. Create detection")
        print("4. Create classification (with arrays)")
        print("5. Query data")
        print("6. Test complete workflow")
        print("0. Exit")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == '0':
            print("Goodbye!")
            break
        elif choice == '1':
            list_devices()
        elif choice == '2':
            create_device()
        elif choice == '3':
            create_detection()
        elif choice == '4':
            create_classification_with_arrays()
        elif choice == '5':
            query_data()
        elif choice == '6':
            test_complete_workflow()
        else:
            print("Invalid option")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")