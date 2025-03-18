"""
API endpoints for plant detection and classification.
This module provides functions to interact with the Sensing Garden API.
"""
import json
import base64
from typing import Optional, Dict, Any
from datetime import datetime
import requests

# Placeholder for the base URL, to be replaced later
BASE_URL = "http://localhost:8000"  # This will be replaced later

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
    """
    # Prepare payload
    payload = _prepare_common_payload(device_id, model_id, image_data, timestamp)
    
    # Send request
    response = requests.post(
        f"{BASE_URL}/detections",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()

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
    """
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
    
    # Send request
    response = requests.post(
        f"{BASE_URL}/classifications",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()
