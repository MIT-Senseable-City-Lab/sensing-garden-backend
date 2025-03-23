"""
API endpoints for POST operations in Sensing Garden API.
This module provides functions to interact with the write operations of the API.
"""
import base64
from typing import Optional, Dict, Any, List

from .client import SensingGardenClient


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
    client: SensingGardenClient,
    device_id: str,
    model_id: str,
    image_data: bytes,
    timestamp: str,
    bounding_box: List[float]
) -> Dict[str, Any]:
    """
    Submit a detection request to the API.
    
    Args:
        client: SensingGardenClient instance
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
    return client.post("detections", payload)


def send_classification_request(
    client: SensingGardenClient,
    device_id: str,
    model_id: str,
    image_data: bytes,
    family: str,
    genus: str,
    species: str,
    family_confidence: float,
    genus_confidence: float,
    species_confidence: float,
    timestamp: str
) -> Dict[str, Any]:
    """
    Submit a classification request to the API.
    
    Args:
        client: SensingGardenClient instance
        device_id: Unique identifier for the device
        model_id: Identifier for the model to use for classification
        image_data: Raw image data as bytes
        family: Taxonomic family of the plant
        genus: Taxonomic genus of the plant
        species: Taxonomic species of the plant
        family_confidence: Confidence score for family classification (0-1)
        genus_confidence: Confidence score for genus classification (0-1)
        species_confidence: Confidence score for species classification (0-1)
        timestamp: ISO-8601 formatted timestamp
        
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
    return client.post("classifications", payload)
