"""
API endpoints for POST operations in Sensing Garden API.
This module provides functions to interact with the write operations of the API.
"""
import base64
import os
from typing import Optional, Dict, Any, Callable, TypeVar, cast
import requests

# Configuration variables loaded from environment
API_KEY = os.environ.get("SENSING_GARDEN_API_KEY", "gMVUsSGzdZ5JgLgpadHtA9yd3Jz5THYs2pEPP7Al")
BASE_URL = os.environ.get("API_BASE_URL", "https://linyz44pd6.execute-api.us-east-1.amazonaws.com")

def set_base_url(url: str) -> None:
    """
    Set the base URL for API requests. This is useful for testing.
    
    Args:
        url: Base URL for the API
    """
    global BASE_URL
    BASE_URL = url

# Type variable for generic function return types
T = TypeVar('T', bound=Dict[str, Any])

def _validate_base_url() -> None:
    """Validate that the base URL is set"""
    if not BASE_URL:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")

def _make_api_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a request to the API with proper error handling.
    
    Args:
        endpoint: API endpoint (without base URL)
        payload: Request payload
        
    Returns:
        API response as dictionary
    
    Raises:
        ValueError: If BASE_URL is not set
        requests.HTTPError: For HTTP error responses
    """
    _validate_base_url()
    
    response = requests.post(
        f"{BASE_URL}/{endpoint}",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY
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
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Prepare common payload data for API requests.
    
    Args:
        device_id: Unique identifier for the device
        model_id: Identifier for the model to use
        image_data: Raw image data as bytes
        timestamp: ISO-8601 formatted timestamp (optional)
        
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
        "image": base64_image
    }
    
    # Add timestamp if provided, otherwise server will generate
    if timestamp:
        payload["timestamp"] = timestamp
    
    return payload

def send_detection_request(
    device_id: str,
    model_id: str,
    image_data: bytes,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit a detection request to the API.
    
    Args:
        device_id: Unique identifier for the device
        model_id: Identifier for the model to use for detection
        image_data: Raw image data as bytes
        timestamp: ISO-8601 formatted timestamp (optional)
        
    Returns:
        API response as dictionary
        
    Raises:
        ValueError: If required parameters are invalid
        requests.HTTPError: For HTTP error responses
    """
    # Prepare payload
    payload = _prepare_common_payload(device_id, model_id, image_data, timestamp)
    
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

def send_model_request(
    model_id: str,
    device_id: str,
    name: str,
    version: str,
    description: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit a model creation request to the API.
    
    Args:
        model_id: Unique identifier for the model
        device_id: Unique identifier for the device
        name: Name of the model
        version: Version string for the model
        description: Description of the model
        metadata: Optional metadata for the model
        timestamp: ISO-8601 formatted timestamp (optional)
        
    Returns:
        API response as dictionary
        
    Raises:
        ValueError: If required parameters are invalid
        requests.HTTPError: For HTTP error responses
    """
    # Validate required parameters
    if not model_id or not device_id or not name or not version:
        raise ValueError("model_id, device_id, name, and version must be provided")
    
    # Create payload with required fields according to the API schema
    payload = {
        "model_id": model_id,
        "device_id": device_id,
        "name": name,
        "version": version,
        "description": description
    }
    
    # Add optional fields if provided
    if metadata:
        payload["metadata"] = metadata
    
    if timestamp:
        payload["timestamp"] = timestamp
    
    # Make API request
    return _make_api_request("models", payload)
