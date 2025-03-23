#!/usr/bin/env python3
"""
Model API endpoints for the Sensing Garden Backend.

This module provides functions for creating and managing models in the Sensing Garden API.
"""
from typing import Any, Dict, Optional

import requests

# Import the centralized configuration
from api_config import get_base_url, set_base_url, get_auth_headers

# Note: Configuration is now managed by the api_config module

def _make_api_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make an API request to the specified endpoint.
    
    Args:
        endpoint: API endpoint path (e.g., "models")
        payload: Request payload data
        
    Returns:
        API response as dictionary
        
    Raises:
        requests.HTTPError: For HTTP error responses
    """
    # Prepare request URL and headers using the config module
    url = f"{get_base_url()}/{endpoint}"
    headers = get_auth_headers()
    
    # Send request
    response = requests.post(url, json=payload, headers=headers)
    
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
