"""
API endpoints for POST operations in Sensing Garden API.
This module provides functions to interact with the write operations of the API.
"""
import json
import base64
from typing import Optional, Dict, Any
from datetime import datetime
import requests

import os

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
    # BASE_URL should always be set now, but just in case
    if BASE_URL is None:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")
        
    # Prepare payload
    payload = _prepare_common_payload(device_id, model_id, image_data, timestamp)
    
    # Send request
    response = requests.post(
        f"{BASE_URL}/detections",
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
    # BASE_URL should always be set now, but just in case
    if BASE_URL is None:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")
        
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
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()

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
    """
    # BASE_URL should always be set now, but just in case
    if BASE_URL is None:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")
        
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
    
    # Send request
    response = requests.post(
        f"{BASE_URL}/models",
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
