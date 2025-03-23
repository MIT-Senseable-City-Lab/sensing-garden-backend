"""
API endpoints for POST operations in Sensing Garden API.
This module provides functions to interact with the write operations of the API.
"""
import base64
from typing import Optional, Dict, Any, Callable, TypeVar, cast, List
import os
import requests

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file if it exists
except ImportError:
    pass  # dotenv is not required, just a convenience

# Type variable for generic function return types
T = TypeVar('T', bound=Dict[str, Any])

# Base URL validation is now handled by the api_config module

def _make_api_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a request to the API with proper error handling.
    
    Args:
        endpoint: API endpoint (without base URL)
        payload: Request payload
        
    Returns:
        API response as dictionary
    
    Raises:
        ValueError: If environment variables are not set
        requests.HTTPError: For HTTP error responses
    """
    # Get API configuration from environment variables
    api_key = os.environ.get("SENSING_GARDEN_API_KEY")
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
        
    base_url = os.environ.get("API_BASE_URL")
    if not base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    # Make the request
    response = requests.post(
        f"{base_url}/{endpoint}",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()

def _prepare_common_payload(
    device_id: str,
    model_id: str,
    image_data: bytes,
    timestamp: str
) -> Dict[str, Any]:
    """
    Prepare common payload data for API requests.
    
    Args:
        device_id: Unique identifier for the device
        model_id: Identifier for the model to use
        image_data: Raw image data as bytes
        timestamp: ISO-8601 formatted timestamp
        
    Returns:
        Dictionary with common payload fields
    """
    if not device_id or not model_id:
        raise ValueError("device_id and model_id must be provided")
    
    if not image_data:
        raise ValueError("image_data cannot be empty")
    
    # Convert image to base64
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # Create payload with required fields
    payload = {
        "device_id": device_id,
        "model_id": model_id,
        "image": base64_image,
        "timestamp": timestamp
    }
    
    return payload

def send_detection_request(
    device_id: str,
    model_id: str,
    image_data: bytes,
    timestamp: str,
    bounding_box: List[float]
) -> Dict[str, Any]:
    """
    Submit a detection request to the API.
    
    Args:
        device_id: Unique identifier for the device
        model_id: Identifier for the model to use for detection
        image_data: Raw image data as bytes
        timestamp: ISO-8601 formatted timestamp
        bounding_box: Bounding box coordinates
        
    Returns:
        API response as dictionary
        
    Raises:
        ValueError: If required parameters are invalid
        requests.HTTPError: For HTTP error responses
    """
    # Prepare payload
    payload = _prepare_common_payload(device_id, model_id, image_data, timestamp)
    
    payload['bounding_box'] = bounding_box
    
    # Make API request
    return _make_api_request("detections", payload)

def send_classification_request(
    device_id: str,
    model_id: str,
    image_data: bytes,
    family: str,
    genus: str,
    species: str,
    family_confidence: float,
    genus_confidence: float,
    species_confidence: float,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit a classification request to the API.
    
    Args:
        device_id: Unique identifier for the device
        model_id: Identifier for the model to use for classification
        image_data: Raw image data as bytes
        family: Taxonomic family of the plant
        genus: Taxonomic genus of the plant
        species: Taxonomic species of the plant
        family_confidence: Confidence score for family classification (0-1)
        genus_confidence: Confidence score for genus classification (0-1)
        species_confidence: Confidence score for species classification (0-1)
        timestamp: ISO-8601 formatted timestamp (optional)
        
    Returns:
        API response as dictionary
        
    Raises:
        ValueError: If required parameters are invalid
        requests.HTTPError: For HTTP error responses
    """
    # Validate confidence scores
    for name, value in [
        ("family_confidence", family_confidence),
        ("genus_confidence", genus_confidence),
        ("species_confidence", species_confidence)
    ]:
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1, got {value}")
    
    # Validate taxonomic data
    for name, value in [("family", family), ("genus", genus), ("species", species)]:
        if not value:
            raise ValueError(f"{name} cannot be empty")
    
    # Prepare common payload
    if timestamp is None:
        raise ValueError("timestamp must be provided")
    payload = _prepare_common_payload(device_id, model_id, image_data, timestamp)
    
    # Add classification-specific fields
    classification_fields = {
        "family": family,
        "genus": genus,
        "species": species,
        "family_confidence": family_confidence,
        "genus_confidence": genus_confidence,
        "species_confidence": species_confidence
    }
    payload.update(classification_fields)
    
    # Make API request
    return _make_api_request("classifications", payload)
