"""
Read API endpoints for plant detection and classification data.
This module provides functions to interact with the read operations of the Sensing Garden API.
"""
import json
from typing import Dict, List, Optional, Any
import requests

# Placeholder for the base URL, to be replaced later
BASE_URL = "http://localhost:8000"  # This will be replaced at runtime

def get_models(
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a list of models from the API.
    
    Args:
        device_id: Optional filter by device ID
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of models to return
        next_token: Token for pagination
        
    Returns:
        API response as dictionary
    """
    # Build query parameters
    params = {}
    if device_id:
        params['device_id'] = device_id
    if model_id:
        params['model_id'] = model_id
    if start_time:
        params['start_time'] = start_time
    if end_time:
        params['end_time'] = end_time
    if limit != 100:
        params['limit'] = str(limit)
    if next_token:
        params['next_token'] = next_token
    
    # Send request
    response = requests.get(
        f"{BASE_URL}/models",
        params=params,
        headers={"Content-Type": "application/json"}
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()

def get_detections(
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a list of detections from the API.
    
    Args:
        device_id: Optional filter by device ID
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of detections to return
        next_token: Token for pagination
        
    Returns:
        API response as dictionary
    """
    # Build query parameters
    params = {}
    if device_id:
        params['device_id'] = device_id
    if model_id:
        params['model_id'] = model_id
    if start_time:
        params['start_time'] = start_time
    if end_time:
        params['end_time'] = end_time
    if limit != 100:
        params['limit'] = str(limit)
    if next_token:
        params['next_token'] = next_token
    
    # Send request
    response = requests.get(
        f"{BASE_URL}/detections",
        params=params,
        headers={"Content-Type": "application/json"}
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()

def get_classifications(
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a list of classifications from the API.
    
    Args:
        device_id: Optional filter by device ID
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of classifications to return
        next_token: Token for pagination
        
    Returns:
        API response as dictionary
    """
    # Build query parameters
    params = {}
    if device_id:
        params['device_id'] = device_id
    if model_id:
        params['model_id'] = model_id
    if start_time:
        params['start_time'] = start_time
    if end_time:
        params['end_time'] = end_time
    if limit != 100:
        params['limit'] = str(limit)
    if next_token:
        params['next_token'] = next_token
    
    # Send request
    response = requests.get(
        f"{BASE_URL}/classifications",
        params=params,
        headers={"Content-Type": "application/json"}
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()

def set_base_url(url: str) -> None:
    """
    Set the base URL for API requests.
    
    Args:
        url: Base URL for the API
    """
    global BASE_URL
    BASE_URL = url
