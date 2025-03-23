"""
API endpoints for GET operations in Sensing Garden API.
This module provides functions to interact with the read operations of the API.
"""
from typing import Dict, List, Optional, Any, TypeVar, Mapping, cast

from .client import SensingGardenClient

# Type variable for generic function return types
T = TypeVar('T', bound=Dict[str, Any])


def _build_common_params(
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
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
        sort_by: Attribute to sort by (e.g., 'timestamp', 'device_id')
        sort_desc: If True, sort in descending order, otherwise ascending
        
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
    if sort_by:
        params['sort_by'] = sort_by
        # Always include sort_desc when sort_by is specified
        params['sort_desc'] = str(sort_desc).lower()
    
    return params


def get_models(
    client: SensingGardenClient,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Dict[str, Any]:
    """
    Get a list of models from the API.
    
    Args:
        client: SensingGardenClient instance
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of models to return
        next_token: Token for pagination
        sort_by: Attribute to sort by (e.g., 'timestamp', 'name', 'version')
        sort_desc: If True, sort in descending order, otherwise ascending
        
    Returns:
        API response as dictionary
    
    Raises:
        requests.HTTPError: For HTTP error responses
        ValueError: If any parameter is invalid
    """
    # Create a modified parameter set without device_id (not used for models)
    params = _build_common_params(None, model_id, start_time, end_time, limit, next_token, sort_by, sort_desc)
    # Remove device_id from params if it was added (will be None)
    if 'device_id' in params:
        del params['device_id']
    return client.get('models', params)


def get_detections(
    client: SensingGardenClient,
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Dict[str, Any]:
    """
    Get a list of detections from the API.
    
    Args:
        client: SensingGardenClient instance
        device_id: Optional filter by device ID
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of detections to return
        next_token: Token for pagination
        sort_by: Attribute to sort by (e.g., 'timestamp', 'device_id')
        sort_desc: If True, sort in descending order, otherwise ascending
        
    Returns:
        API response as dictionary
    
    Raises:
        ValueError: If limit or sort_order is invalid
        requests.HTTPError: For HTTP error responses
    """
    params = _build_common_params(device_id, model_id, start_time, end_time, limit, next_token, sort_by, sort_desc)
    return client.get('detections', params)


def get_classifications(
    client: SensingGardenClient,
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Dict[str, Any]:
    """
    Get a list of classifications from the API.
    
    Args:
        client: SensingGardenClient instance
        device_id: Optional filter by device ID
        model_id: Optional filter by model ID
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        limit: Maximum number of classifications to return
        next_token: Token for pagination
        sort_by: Attribute to sort by (e.g., 'timestamp', 'family', 'species')
        sort_desc: If True, sort in descending order, otherwise ascending
        
    Returns:
        API response as dictionary
    
    Raises:
        ValueError: If limit or sort_order is invalid
        requests.HTTPError: For HTTP error responses
    """
    params = _build_common_params(device_id, model_id, start_time, end_time, limit, next_token, sort_by, sort_desc)
    return client.get('classifications', params)
