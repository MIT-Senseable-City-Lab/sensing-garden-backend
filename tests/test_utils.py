#!/usr/bin/env python3
"""
Shared utilities for Sensing Garden API tests.
This module provides common functionality used across all test files.
"""
import io
import json
import os
import random
import string
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, List, Union

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw

# Import the Sensing Garden client package
from sensing_garden_client import SensingGardenClient

# Load environment variables
load_dotenv()

# Default test device ID - use this across all tests for consistency
DEFAULT_TEST_DEVICE_ID = "test-device"

# Default test model ID - use this for classification and detection tests
DEFAULT_TEST_MODEL_ID = "test-model-2025"

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_client() -> SensingGardenClient:
    """
    Get an initialized SensingGardenClient instance, with AWS credentials if present.
    
    Returns:
        SensingGardenClient: Initialized client
        
    Raises:
        ValueError: If required environment variables are not set
    """
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")

    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")

    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")

    # Patch SensingGardenClient to pass AWS credentials to VideosClient if present
    from sensing_garden_client.client import SensingGardenClient as _SGC

    client = _SGC(
        base_url=api_base_url,
        api_key=api_key,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_region=aws_region,
        aws_session_token=aws_session_token
    )
    return client

def create_test_image() -> bytes:
    """
    Create a test image with a timestamp.
    
    Returns:
        bytes: JPEG image data
    """
    # Create a simple image with text
    img = Image.new('RGB', (300, 200), color=(73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10, 10), f"Test Image {datetime.now().isoformat()}", fill=(255, 255, 0))
    
    # Save to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    
    # Return raw bytes (not base64 encoded)
    return img_byte_arr.getvalue()

def create_test_video() -> bytes:
    """
    Create a simple binary file that simulates a video.
    
    Returns:
        bytes: Random binary data
    """
    # In a real scenario, this would be actual video data
    video_data = bytearray([random.randint(0, 255) for _ in range(1024)])
    return bytes(video_data)

def generate_random_string(length=8) -> str:
    """
    Generate a random string of specified length.
    
    Args:
        length: Length of string to generate
        
    Returns:
        str: Random string
    """
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def generate_random_confidence() -> float:
    """
    Generate a random confidence value between 0.5 and 1.0.
    
    Returns:
        float: Random confidence value
    """
    return random.uniform(0.5, 1.0)

def generate_random_bounding_box() -> List[float]:
    """
    Generate a random bounding box with coordinates between 0 and 1.
    
    Returns:
        List[float]: Bounding box as [x1, y1, x2, y2]
    """
    x1 = random.uniform(0, 0.8)  # Ensure room for width
    y1 = random.uniform(0, 0.8)  # Ensure room for height
    width = random.uniform(0.1, 0.8 - x1)  # Ensure valid width
    height = random.uniform(0.1, 0.8 - y1)  # Ensure valid height
    return [x1, y1, x1 + width, y1 + height]

# Predefined lists of test names
TEST_FAMILIES = [
    "test_family_rosaceae",
    "test_family_fabaceae",
    "test_family_salicaceae",
    "test_family_pinaceae"
]

TEST_GENERA = [
    "test_genus_prunus",
    "test_genus_quercus",
    "test_genus_salix",
    "test_genus_pinus"
]

TEST_SPECIES = [
    "test_species_prunus_persica",
    "test_species_quercus_robur",
    "test_species_salix_alba",
    "test_species_pinus_sylvestris"
]

def get_random_test_name(name_list: List[str]) -> str:
    """
    Get a random name from a predefined list.
    
    Args:
        name_list: List of names to choose from
        
    Returns:
        str: Random name from the list
    """
    return random.choice(name_list)

def print_response(response_data: Dict[str, Any]) -> None:
    """
    Print API response data in a formatted way.
    
    Args:
        response_data: Response data from API
    """
    print(f"Response body: {json.dumps(response_data, indent=2, cls=DecimalEncoder)}")
