"""
Model operations for the Sensing Garden API.

This module provides functionality for creating and retrieving models.
"""
from typing import Dict, Optional, Any

from .client import BaseClient
from .shared import build_common_params


class ModelsClient:
    """Client for working with models in the Sensing Garden API."""

    def __init__(self, base_client: BaseClient):
        """
        Initialize the models client.
        
        Args:
            base_client: The base client for API communication
        """
        self._client = base_client
    
    def create(
        self,
        model_id: str,
        name: str,
        version: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new model in the Sensing Garden API.
        
        Args:
            model_id: Unique identifier for the model
            name: Name of the model
            version: Version string for the model
            description: Description of the model
            metadata: Optional metadata for the model
            timestamp: ISO-8601 formatted timestamp (optional)
            
        Returns:
            API response containing the created model
            
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
        return self._client.post("models", payload)
    
    def fetch(
        self,
        model_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        next_token: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_desc: bool = False
    ) -> Dict[str, Any]:
        """
        Retrieve models from the Sensing Garden API.
        
        Args:
            model_id: Optional filter by model ID
            start_time: Optional start time for filtering (ISO-8601)
            end_time: Optional end time for filtering (ISO-8601)
            limit: Maximum number of items to return
            next_token: Token for pagination
            sort_by: Attribute to sort by (e.g., 'timestamp')
            sort_desc: If True, sort in descending order, otherwise ascending
            
        Returns:
            API response with matching models
            
        Raises:
            requests.HTTPError: For HTTP error responses
        """
        # Build query parameters
        params = build_common_params(
            model_id=model_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            next_token=next_token,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        # Make API request
        return self._client.get("models", params)
