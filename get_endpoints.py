"""
API endpoints for GET operations in Sensing Garden API.
This module provides functions to interact with the read operations of the API.
"""
import json
from typing import Dict, List, Optional, Any
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
    # BASE_URL should always be set now, but just in case
    if BASE_URL is None:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")
        
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
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }
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
    # BASE_URL should always be set now, but just in case
    if BASE_URL is None:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")
        
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
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }
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
    # BASE_URL should always be set now, but just in case
    if BASE_URL is None:
        raise ValueError("Base URL not set. Check environment variables or call set_base_url().")
        
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
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
    return response.json()
