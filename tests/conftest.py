"""
Test configuration and fixtures for sensing garden backend tests.

Only includes fixtures that support real infrastructure testing.
Mock fixtures have been removed to prevent false testing confidence.
"""
import pytest
import os
import sys

# Add lambda src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda', 'src'))

@pytest.fixture
def device_id():
    """Test device ID fixture."""
    return "test-device-001"

@pytest.fixture
def model_id():
    """Test model ID fixture."""
    return "yolov8n-insects-test-v1.0"

@pytest.fixture
def sample_base64_image():
    """Sample base64 encoded 1x1 pixel image."""
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

@pytest.fixture
def basic_classification_data(device_id, model_id, sample_base64_image):
    """Basic classification data without environment data."""
    return {
        "device_id": device_id,
        "model_id": model_id,
        "image": sample_base64_image,
        "family": "Nymphalidae",
        "genus": "Vanessa",
        "species": "cardui",
        "family_confidence": 0.95,
        "genus_confidence": 0.87,
        "species_confidence": 0.82
    }

@pytest.fixture
def environmental_data():
    """Sample environmental sensor data."""
    return {
        "pm1p0": 12.5,
        "pm2p5": 18.3,
        "pm4p0": 22.1,
        "pm10p0": 28.7,
        "ambient_humidity": 65.2,
        "ambient_temperature": 23.4,
        "voc_index": 150,
        "nox_index": 75
    }

@pytest.fixture
def location_data():
    """Sample GPS location data."""
    return {
        "lat": 40.7128,
        "long": -74.0060,
        "alt": 10.5
    }

@pytest.fixture
def classification_with_environment(basic_classification_data, environmental_data, location_data):
    """Classification data with environment and location data."""
    data = basic_classification_data.copy()
    data["location"] = location_data
    data["environment"] = environmental_data
    data["track_id"] = "test_track_001"
    data["bounding_box"] = [150, 200, 50, 40]
    return data