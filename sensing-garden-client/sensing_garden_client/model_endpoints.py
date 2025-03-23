"""
Model API endpoints for the Sensing Garden Backend.

This module provides functions for creating and managing models in the Sensing Garden API.
"""
from typing import Any, Dict, Optional

from .client import SensingGardenClient


def send_model_request(
    client: SensingGardenClient,
    model_id: str,
    name: str,
    version: str,
    description: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit a model creation request to the API.
    
    Args:
        client: SensingGardenClient instance
        model_id: Unique identifier for the model
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
    if not model_id or not name or not version:
        raise ValueError("model_id, name, and version must be provided")
    
    # Create payload with required fields according to the API schema
    payload = {
        "model_id": model_id,
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
    return client.post("models", payload)
