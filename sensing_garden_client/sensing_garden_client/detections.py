"""
Detection operations for the Sensing Garden API.

This module provides functionality for creating and retrieving detections.
"""
from typing import Dict, List, Optional, Any

from .client import BaseClient
from .shared import build_common_params, prepare_image_payload


class DetectionsClient:
    """Client for working with detections in the Sensing Garden API."""

    def __init__(self, base_client: BaseClient):
        """
        Initialize the detections client.
        
        Args:
            base_client: The base client for API communication
        """
        self._client = base_client
    
    def add(
        self,
        device_id: str,
        model_id: str,
        image_data: bytes,
        bounding_box: List[float],
        timestamp: str
    ) -> Dict[str, Any]:
        """
        Submit a detection to the Sensing Garden API.
        
        Args:
            device_id: Unique identifier for the device
            model_id: Identifier for the model used
            image_data: Raw image data as bytes
            bounding_box: Bounding box coordinates [x1, y1, x2, y2]
            timestamp: ISO-8601 formatted timestamp
            
        Returns:
            API response with the created detection
            
        Raises:
            ValueError: If required parameters are invalid
            requests.HTTPError: For HTTP error responses
        """
        # Validate bounding_box
        if not isinstance(bounding_box, list) or len(bounding_box) != 4:
            raise ValueError("bounding_box must be a list of 4 float values")
        
        # Prepare base payload with common fields
        payload = prepare_image_payload(
            device_id=device_id,
            model_id=model_id,
            image_data=image_data,
            timestamp=timestamp
        )
        
        # Add detection-specific fields
        payload["bounding_box"] = bounding_box
        
        # Make API request
        return self._client.post("detections", payload)
    
    def fetch(
        self,
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
        Retrieve detections from the Sensing Garden API.
        
        Args:
            device_id: Optional filter by device ID
            model_id: Optional filter by model ID
            start_time: Optional start time for filtering (ISO-8601)
            end_time: Optional end time for filtering (ISO-8601)
            limit: Maximum number of items to return
            next_token: Token for pagination
            sort_by: Attribute to sort by (e.g., 'timestamp')
            sort_desc: If True, sort in descending order, otherwise ascending
            
        Returns:
            API response with matching detections
            
        Raises:
            requests.HTTPError: For HTTP error responses
        """
        # Build query parameters
        params = build_common_params(
            device_id=device_id,
            model_id=model_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            next_token=next_token,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        # Make API request
        return self._client.get("detections", params)
