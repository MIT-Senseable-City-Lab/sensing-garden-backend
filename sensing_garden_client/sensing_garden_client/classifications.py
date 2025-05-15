"""
Classification operations for the Sensing Garden API.

This module provides functionality for creating and retrieving classifications.
"""
from typing import Dict, Optional, Any, Union

from .client import BaseClient
from .shared import build_common_params, prepare_image_payload


class ClassificationsClient:
    """Client for working with classifications in the Sensing Garden API."""

    def __init__(self, base_client: BaseClient):
        """
        Initialize the classifications client.
        
        Args:
            base_client: The base client for API communication
        """
        self._client = base_client
    
    def add(
        self,
        device_id: str,
        model_id: str,
        image_data: bytes,
        family: str,
        genus: str,
        species: str,
        family_confidence: Union[float, str],
        genus_confidence: Union[float, str],
        species_confidence: Union[float, str],
        timestamp: str,
        bounding_box: Optional[Any] = None,
        track_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit a classification to the Sensing Garden API.
        
        Args:
            device_id: Unique identifier for the device
            model_id: Identifier for the model used
            image_data: Raw image data as bytes
            family: Plant family name
            genus: Plant genus name
            species: Plant species name
            family_confidence: Confidence score for family classification (0-1)
            genus_confidence: Confidence score for genus classification (0-1)
            species_confidence: Confidence score for species classification (0-1)
            timestamp: ISO-8601 formatted timestamp
            bounding_box: Optional bounding box coordinates [x1, y1, x2, y2] or similar structure
            track_id: Optional string for tracking related classifications or external references
            metadata: Optional dict for arbitrary metadata to future-proof client extensions
        Returns:
            API response with the created classification
        Raises:
            ValueError: If required parameters are invalid
            requests.HTTPError: For HTTP error responses
        """
        # Prepare base payload with common fields
        payload = prepare_image_payload(
            device_id=device_id,
            model_id=model_id,
            image_data=image_data,
            timestamp=timestamp
        )
        
        # Add classification-specific fields
        payload.update({
            "family": family,
            "genus": genus,
            "species": species,
            "family_confidence": family_confidence,
            "genus_confidence": genus_confidence,
            "species_confidence": species_confidence
        })
        if bounding_box is not None:
            payload["bounding_box"] = bounding_box
        if track_id is not None:
            payload["track_id"] = track_id
        if metadata is not None:
            payload["metadata"] = metadata
        # Make API request
        return self._client.post("classifications", payload)
    
    def count(
        self,
        device_id: Optional[str] = None,
        model_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> int:
        """
        Get the count of classifications matching the filter parameters.
        Args:
            device_id: Optional filter by device ID
            model_id: Optional filter by model ID
            start_time: Optional start time for filtering (ISO-8601)
            end_time: Optional end time for filtering (ISO-8601)
        Returns:
            Integer count of matching classifications
        Raises:
            requests.HTTPError: For HTTP error responses
        """
        params = build_common_params(
            device_id=device_id,
            model_id=model_id,
            start_time=start_time,
            end_time=end_time,
            limit=None, next_token=None, sort_by=None, sort_desc=None
        )
        resp = self._client.get("classifications/count", params)
        return resp["count"]

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
        Retrieve classifications from the Sensing Garden API.
        
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
            API response with matching classifications
            
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
        return self._client.get("classifications", params)
