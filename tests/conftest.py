"""
Test configuration and fixtures for sensing garden backend tests.
"""
import pytest
import os
import sys
from unittest.mock import Mock, patch
from decimal import Decimal

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

@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB client."""
    with patch('boto3.resource') as mock_resource:
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        yield mock_table

@pytest.fixture
def mock_s3():
    """Mock S3 client for image uploads."""
    with patch('boto3.client') as mock_client:
        mock_s3_client = Mock()
        mock_client.return_value = mock_s3_client
        # Mock successful upload
        mock_s3_client.put_object.return_value = {'ETag': '"test-etag"'}
        yield mock_s3_client

@pytest.fixture
def mock_env_vars():
    """Mock environment variables."""
    env_vars = {
        'ENVIRONMENT': 'test',
        'IMAGES_BUCKET': 'test-images-bucket',
        'VIDEOS_BUCKET': 'test-videos-bucket'
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars

@pytest.fixture(autouse=True)
def setup_test_environment(mock_env_vars):
    """Automatically set up test environment for all tests."""
    pass