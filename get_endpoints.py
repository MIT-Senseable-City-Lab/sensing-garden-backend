"""
API endpoints for GET operations in Sensing Garden API.
This module provides functions to interact with the read operations of the API.
"""
from typing import Dict, List, Optional, Any, TypeVar, Mapping, cast
import requests

# Import the centralized configuration
from api_config import get_base_url, set_base_url, get_auth_headers

# Note: Configuration is now managed by the api_config module

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
    if limit != 100:
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
        ValueError: If BASE_URL is not set
        requests.HTTPError: For HTTP error responses
    """
    # Use centralized configuration
    response = requests.get(
        f"{get_base_url()}/{endpoint}",
        params=params,
        headers=get_auth_headers()
    )
    
    # Raise exception for error responses
    response.raise_for_status()
    
    # Return parsed JSON response
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
    # Validate input parameters
    if limit <= 0:
        raise ValueError(f"limit must be a positive integer, got {limit}")
    
    # Build query parameters
    params = _build_common_params(
        device_id=device_id,
        model_id=model_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        next_token=next_token
    )
    
    # Make API request
    return _make_api_request("models", params)

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
    # Validate input parameters
    if limit <= 0:
        raise ValueError(f"limit must be a positive integer, got {limit}")
    
    # Build query parameters
    params = _build_common_params(
        device_id=device_id,
        model_id=model_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        next_token=next_token
    )
    
    # Make API request
    return _make_api_request("detections", params)

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
    # Validate input parameters
    if limit <= 0:
        raise ValueError(f"limit must be a positive integer, got {limit}")
    
    # Build query parameters
    params = _build_common_params(
        device_id=device_id,
        model_id=model_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        next_token=next_token
    )
    
    # Make API request
    return _make_api_request("classifications", params)
