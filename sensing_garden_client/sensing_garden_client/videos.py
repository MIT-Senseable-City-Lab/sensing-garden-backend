"""
Video operations for the Sensing Garden API.

This module provides functionality for uploading and retrieving videos,
including support for multipart uploads for large video files.
"""
import math
import os
import io
import json
import mimetypes
import requests
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional, Any, Dict, List, BinaryIO, Union, Tuple, Callable

from .client import BaseClient
from .shared import build_common_params, prepare_video_payload, prepare_multipart_initiate_payload


class VideosClient:
    """Client for working with videos in the Sensing Garden API."""

    # Default chunk size for multipart uploads (5MB)
    DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024
    
    # Maximum size for standard uploads (5MB)
    MAX_STANDARD_UPLOAD_SIZE = 5 * 1024 * 1024
    
    # Default number of retry attempts for failed uploads
    DEFAULT_MAX_RETRIES = 3
    
    # S3 bucket name for videos
    S3_BUCKET_NAME = "scl-sensing-garden-videos"

    def __init__(self, base_client: BaseClient):
        """
        Initialize the videos client.
        
        Args:
            base_client: The base client for API communication
        """
        self._client = base_client
        self._s3_client = boto3.client('s3')
    
    def upload(
        self,
        device_id: str,
        video_data: bytes,
        description: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_multipart: bool = False,
        content_type: str = 'video/mp4',
        chunk_size: int = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Upload a video to the Sensing Garden API.
        
        Args:
            device_id: Unique identifier for the device
            video_data: Raw video data as bytes
            description: Description of the video content
            timestamp: ISO-8601 formatted timestamp (optional)
            metadata: Additional metadata about the video (optional)
            use_multipart: If True, use multipart upload for large videos (recommended for videos > 5MB)
            content_type: MIME type of the video (default: 'video/mp4')
            chunk_size: Size of each chunk in bytes for multipart uploads (default: 5MB)
            
        Returns:
            API response with the uploaded video information
            
        Raises:
            ValueError: If required parameters are invalid
            requests.HTTPError: For HTTP error responses
        """
        # For large videos, automatically use multipart upload
        if len(video_data) > self.MAX_STANDARD_UPLOAD_SIZE:
            use_multipart = True
        
        if use_multipart:
            return self.upload_multipart(
                device_id=device_id,
                video_data=video_data,
                description=description,
                content_type=content_type,
                timestamp=timestamp,
                metadata=metadata,
                chunk_size=chunk_size or self.DEFAULT_CHUNK_SIZE,
                max_retries=max_retries,
                progress_callback=progress_callback
            )
        else:
            # Use standard upload for smaller videos
            payload = prepare_video_payload(
                device_id=device_id,
                video_data=video_data,
                description=description,
                timestamp=timestamp,
                metadata=metadata
            )
            
            # Make API request
            return self._client.post("videos", payload)
    
    def upload_multipart(
        self,
        device_id: str,
        video_data: bytes,
        description: str,
        content_type: str = 'video/mp4',
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Upload a large video using S3's native multipart upload.
        
        Args:
            device_id: Unique identifier for the device
            video_data: Raw video data as bytes
            description: Description of the video content
            content_type: MIME type of the video
            timestamp: ISO-8601 formatted timestamp (optional)
            metadata: Additional metadata about the video (optional)
            chunk_size: Size of each chunk in bytes
            max_retries: Maximum number of retry attempts for failed uploads
            progress_callback: Optional callback function to report upload progress
                              Args: (bytes_uploaded, total_bytes, part_number)
            
        Returns:
            API response with the uploaded video information
            
        Raises:
            ValueError: If required parameters are invalid
            ClientError: For AWS S3 errors
        """
        if not device_id:
            raise ValueError("device_id must be provided")
        
        if not video_data:
            raise ValueError("video_data cannot be empty")
        
        if not description:
            raise ValueError("description must be provided")
        
        # Generate a timestamp if not provided
        if not timestamp:
            from datetime import datetime
            timestamp = datetime.now().isoformat()
        
        # Format timestamp for the S3 key
        formatted_timestamp = timestamp.replace(':', '-').replace('.', '-').split('+')[0]
        
        # Generate S3 key for the video
        file_extension = self._get_file_extension_from_content_type(content_type)
        s3_key = f"videos/{device_id}/{formatted_timestamp}{file_extension}"
        
        # Prepare metadata for S3
        s3_metadata = {
            'device_id': device_id,
            'description': description,
            'timestamp': timestamp,
            'content_type': content_type
        }
        
        # Add custom metadata if provided
        if metadata:
            s3_metadata['custom_metadata'] = json.dumps(metadata)
        
        # Calculate total parts
        total_size = len(video_data)
        total_parts = math.ceil(total_size / chunk_size)
        bytes_uploaded = 0
        
        try:
            # Step 1: Initiate multipart upload directly with S3
            response = self._s3_client.create_multipart_upload(
                Bucket=self.S3_BUCKET_NAME,
                Key=s3_key,
                ContentType=content_type,
                Metadata={k: str(v) for k, v in s3_metadata.items()}
            )
            upload_id = response['UploadId']
            
            # Step 2: Upload parts with retry logic
            parts = []
            for part_number in range(1, total_parts + 1):
                start_byte = (part_number - 1) * chunk_size
                end_byte = min(start_byte + chunk_size, total_size)
                part_data = video_data[start_byte:end_byte]
                part_size = len(part_data)
                
                # Retry logic for uploading parts
                retry_count = 0
                upload_success = False
                
                while not upload_success and retry_count <= max_retries:
                    try:
                        # Upload the part directly to S3
                        part_response = self._s3_client.upload_part(
                            Bucket=self.S3_BUCKET_NAME,
                            Key=s3_key,
                            PartNumber=part_number,
                            UploadId=upload_id,
                            Body=part_data
                        )
                        
                        # Add the part info to our list
                        parts.append({
                            'PartNumber': part_number,
                            'ETag': part_response['ETag']
                        })
                        
                        upload_success = True
                        
                        # Update progress
                        bytes_uploaded += part_size
                        if progress_callback:
                            progress_callback(bytes_uploaded, total_size, part_number)
                            
                    except ClientError as e:
                        retry_count += 1
                        if retry_count > max_retries:
                            # If we've exceeded max retries, abort the upload and re-raise
                            self._s3_client.abort_multipart_upload(
                                Bucket=self.S3_BUCKET_NAME,
                                Key=s3_key,
                                UploadId=upload_id
                            )
                            raise
            
            # Step 3: Complete the multipart upload
            self._s3_client.complete_multipart_upload(
                Bucket=self.S3_BUCKET_NAME,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            # Step 4: Register the video in the API
            register_payload = {
                'device_id': device_id,
                'description': description,
                'video_key': s3_key,
                'timestamp': timestamp
            }
            
            if metadata:
                register_payload['metadata'] = metadata
                
            # Register the video with the API
            return self._client.post("videos/register", register_payload)
            
        except ClientError as e:
            # Handle S3 errors
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            raise ClientError(e.response, f"S3 error: {error_code} - {error_message}")
        
        # Step 3: Complete multipart upload
        complete_payload = {
            'upload_id': upload_id
        }
        
        return self._client.post("videos/multipart/complete", complete_payload)
    
    def upload_file(
        self,
        device_id: str,
        video_file_path: str,
        description: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        content_type: Optional[str] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Upload a video file from disk using multipart upload for large files.
        
        Args:
            device_id: Unique identifier for the device
            video_file_path: Path to the video file on disk
            description: Description of the video content
            timestamp: ISO-8601 formatted timestamp (optional)
            metadata: Additional metadata about the video (optional)
            content_type: MIME type of the video (if None, will be guessed from file extension)
            chunk_size: Size of each chunk in bytes for multipart uploads
            max_retries: Maximum number of retry attempts for failed uploads
            progress_callback: Optional callback function to report upload progress
                              Args: (bytes_uploaded, total_bytes, part_number)
            
        Returns:
            API response with the uploaded video information
            
        Raises:
            ValueError: If required parameters are invalid
            FileNotFoundError: If the video file doesn't exist
            requests.HTTPError: For HTTP error responses
        """
        if not os.path.exists(video_file_path):
            raise FileNotFoundError(f"Video file not found: {video_file_path}")
        
        # Get file size
        file_size = os.path.getsize(video_file_path)
        
        # Determine content type if not provided
        if content_type is None:
            # Use mimetypes library for more robust content type detection
            guessed_type, _ = mimetypes.guess_type(video_file_path)
            if guessed_type and guessed_type.startswith('video/'):
                content_type = guessed_type
            else:
                # Fallback to extension-based detection
                _, ext = os.path.splitext(video_file_path)
                ext = ext.lower()
                if ext == '.mp4':
                    content_type = 'video/mp4'
                elif ext == '.webm':
                    content_type = 'video/webm'
                elif ext == '.mov':
                    content_type = 'video/quicktime'
                elif ext == '.avi':
                    content_type = 'video/x-msvideo'
                else:
                    content_type = 'video/mp4'  # Default
        
        # For small files, read the whole file and use standard upload
        if file_size <= self.MAX_STANDARD_UPLOAD_SIZE:
            with open(video_file_path, 'rb') as f:
                video_data = f.read()
            
            # Call progress callback if provided
            if progress_callback:
                progress_callback(file_size, file_size, 1)
                
            return self.upload(
                device_id=device_id,
                video_data=video_data,
                description=description,
                timestamp=timestamp,
                metadata=metadata,
                content_type=content_type
            )
        
        # For large files, use multipart upload
        return self._upload_file_multipart(
            device_id=device_id,
            video_file_path=video_file_path,
            description=description,
            timestamp=timestamp,
            metadata=metadata,
            content_type=content_type,
            chunk_size=chunk_size,
            max_retries=max_retries,
            progress_callback=progress_callback
        )
    
    def _upload_file_multipart(
        self,
        device_id: str,
        video_file_path: str,
        description: str,
        content_type: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Internal method to handle multipart upload of a file using S3's native multipart upload.
        
        Args:
            device_id: Unique identifier for the device
            video_file_path: Path to the video file on disk
            description: Description of the video content
            content_type: MIME type of the video
            timestamp: ISO-8601 formatted timestamp (optional)
            metadata: Additional metadata about the video (optional)
            chunk_size: Size of each chunk in bytes
            max_retries: Maximum number of retry attempts for failed uploads
            progress_callback: Optional callback function to report upload progress
            
        Returns:
            API response with the uploaded video information
        """
        file_size = os.path.getsize(video_file_path)
        total_parts = math.ceil(file_size / chunk_size)
        bytes_uploaded = 0
        
        # Generate a timestamp if not provided
        if not timestamp:
            from datetime import datetime
            timestamp = datetime.now().isoformat()
        
        # Format timestamp for the S3 key
        formatted_timestamp = timestamp.replace(':', '-').replace('.', '-').split('+')[0]
        
        # Generate S3 key for the video
        file_extension = self._get_file_extension_from_content_type(content_type)
        s3_key = f"videos/{device_id}/{formatted_timestamp}{file_extension}"
        
        # Prepare metadata for S3
        s3_metadata = {
            'device_id': device_id,
            'description': description,
            'timestamp': timestamp,
            'content_type': content_type
        }
        
        # Add custom metadata if provided
        if metadata:
            s3_metadata['custom_metadata'] = json.dumps(metadata)
        
        try:
            # Step 1: Initiate multipart upload directly with S3
            response = self._s3_client.create_multipart_upload(
                Bucket=self.S3_BUCKET_NAME,
                Key=s3_key,
                ContentType=content_type,
                Metadata={k: str(v) for k, v in s3_metadata.items()}
            )
            upload_id = response['UploadId']
            
            # Step 2: Upload parts with retry logic
            parts = []
            with open(video_file_path, 'rb') as f:
                for part_number in range(1, total_parts + 1):
                    # Read chunk from file
                    part_data = f.read(chunk_size)
                    part_size = len(part_data)
                    
                    if part_size == 0:  # End of file
                        break
                    
                    # Retry logic for uploading parts
                    retry_count = 0
                    upload_success = False
                    
                    while not upload_success and retry_count <= max_retries:
                        try:
                            # Upload the part directly to S3
                            part_response = self._s3_client.upload_part(
                                Bucket=self.S3_BUCKET_NAME,
                                Key=s3_key,
                                PartNumber=part_number,
                                UploadId=upload_id,
                                Body=part_data
                            )
                            
                            # Add the part info to our list
                            parts.append({
                                'PartNumber': part_number,
                                'ETag': part_response['ETag']
                            })
                            
                            upload_success = True
                            
                            # Update progress
                            bytes_uploaded += part_size
                            if progress_callback:
                                progress_callback(bytes_uploaded, file_size, part_number)
                                
                        except ClientError as e:
                            retry_count += 1
                            if retry_count > max_retries:
                                # If we've exceeded max retries, abort the upload and re-raise
                                self._s3_client.abort_multipart_upload(
                                    Bucket=self.S3_BUCKET_NAME,
                                    Key=s3_key,
                                    UploadId=upload_id
                                )
                                raise
            
            # Step 3: Complete the multipart upload
            self._s3_client.complete_multipart_upload(
                Bucket=self.S3_BUCKET_NAME,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            # Step 4: Register the video in the API
            register_payload = {
                'device_id': device_id,
                'description': description,
                'video_key': s3_key,
                'timestamp': timestamp
            }
            
            if metadata:
                register_payload['metadata'] = metadata
                
            # Register the video with the API
            return self._client.post("videos/register", register_payload)
            
        except ClientError as e:
            # Handle S3 errors
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            raise ClientError(e.response, f"S3 error: {error_code} - {error_message}")
    
    def _get_file_extension_from_content_type(self, content_type: str) -> str:
        """Get the file extension based on the content type."""
        if content_type == 'video/mp4':
            return '.mp4'
        elif content_type == 'video/webm':
            return '.webm'
        elif content_type == 'video/quicktime':
            return '.mov'
        elif content_type == 'video/x-msvideo':
            return '.avi'
        else:
            return '.mp4'  # Default extension
    
    def register_video(
        self,
        device_id: str,
        video_key: str,
        description: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Register a video that was uploaded directly to S3.

        Args:
            device_id: Unique identifier for the device
            video_key: The S3 key of the uploaded video
            description: Description of the video content
            timestamp: ISO-8601 formatted timestamp (optional)
            metadata: Additional metadata about the video (optional)

        Returns:
            API response with the registered video information

        Raises:
            requests.HTTPError: For HTTP error responses
        """
        # Prepare request data
        register_payload = {
            'device_id': device_id,
            'video_key': video_key,
            'description': description
        }
        
        # Add timestamp if provided
        if timestamp:
            register_payload['timestamp'] = timestamp
            
        # Add metadata if provided
        if metadata:
            register_payload['metadata'] = metadata
        
        # Make API request to register the video
        response = self._client.post("videos/register", register_payload)
        
        # Return the response data
        return response
    
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
