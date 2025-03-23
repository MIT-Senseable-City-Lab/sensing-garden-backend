"""
API endpoints for GET operations in Sensing Garden API.
This module provides functions to interact with the read operations of the API.
"""
from typing import Dict, List, Optional, Any, TypeVar, Mapping, cast
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

def _build_common_params(
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None
) -> Dict[str, str]:
    """
    Build common query parameters for GET requests.
    
    Args:
        device_id: Optional filter by device ID
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of items to return
        next_token: Token for pagination
        
    Returns:
        Dictionary with query parameters
    """
    # Build query parameters dictionary with only non-None values
    params = {}
    
    if device_id:
        params['device_id'] = device_id
    if model_id:
        params['model_id'] = model_id
    if start_time:
        params['start_time'] = start_time
    if end_time:
        params['end_time'] = end_time
    if limit:
        params['limit'] = str(limit)
    if next_token:
        params['next_token'] = next_token
    
    return params

def _make_api_request(endpoint: str, params: Mapping[str, str] = None) -> Dict[str, Any]:
    """
    Make a request to the API with proper error handling.
    
    Args:
        endpoint: API endpoint (without base URL)
        params: Query parameters
        
    Returns:
        API response as dictionary
    
    Raises:
        ValueError: If environment variables are not set
        requests.HTTPError: For HTTP error responses
    """
    base_url = os.getenv('API_BASE_URL')
    if not base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    url = f"{base_url}/{endpoint}"
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

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
    
    Raises:
        ValueError: If BASE_URL is not set
        requests.HTTPError: For HTTP error responses
    """
    params = _build_common_params(device_id, model_id, start_time, end_time, limit, next_token)
    return _make_api_request('models', params)

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
    
    Raises:
        ValueError: If limit is invalid or BASE_URL is not set
        requests.HTTPError: For HTTP error responses
    """
    params = _build_common_params(device_id, model_id, start_time, end_time, limit, next_token)
    return _make_api_request('detections', params)

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
    
    Raises:
        ValueError: If limit is invalid or BASE_URL is not set
        requests.HTTPError: For HTTP error responses
    """
    params = _build_common_params(device_id, model_id, start_time, end_time, limit, next_token)
    return _make_api_request('classifications', params)
