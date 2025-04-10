"""
Video operations for the Sensing Garden API.

This module provides functionality for uploading and retrieving videos.
"""
from typing import Dict, Optional, Any, Dict

from .client import BaseClient
from .shared import build_common_params, prepare_video_payload


class VideosClient:
    """Client for working with videos in the Sensing Garden API."""

    def __init__(self, base_client: BaseClient):
        """
        Initialize the videos client.
        
        Args:
            base_client: The base client for API communication
        """
        self._client = base_client
    
    def upload(
        self,
        device_id: str,
        video_data: bytes,
        description: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload a video to the Sensing Garden API.
        
        Args:
            device_id: Unique identifier for the device
            video_data: Raw video data as bytes
            description: Description of the video content
            timestamp: ISO-8601 formatted timestamp (optional)
            metadata: Additional metadata about the video (optional)
            
        Returns:
            API response with the uploaded video information
            
        Raises:
            ValueError: If required parameters are invalid
            requests.HTTPError: For HTTP error responses
        """
        # Prepare payload with video data
        payload = prepare_video_payload(
            device_id=device_id,
            video_data=video_data,
            description=description,
            timestamp=timestamp,
            metadata=metadata
        )
        
        # Make API request
        return self._client.post("videos", payload)
    
    def fetch(
        self,
        device_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        next_token: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_desc: bool = False
    ) -> Dict[str, Any]:
        """
        Retrieve videos from the Sensing Garden API.
        
        Args:
            device_id: Optional filter by device ID
            start_time: Optional start time for filtering (ISO-8601)
            end_time: Optional end time for filtering (ISO-8601)
            limit: Maximum number of items to return
            next_token: Token for pagination
            sort_by: Attribute to sort by (e.g., 'timestamp')
            sort_desc: If True, sort in descending order, otherwise ascending
            
        Returns:
            API response with matching videos, including presigned URLs
            
        Raises:
            requests.HTTPError: For HTTP error responses
        """
        # Build query parameters
        params = build_common_params(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            next_token=next_token,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        # Make API request
        return self._client.get("videos", params)
