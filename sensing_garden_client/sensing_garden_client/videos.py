"""
Video operations for the Sensing Garden API.

This module provides functionality for uploading and retrieving videos,
including support for multipart uploads for large video files.
"""
import os
import json
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional, Any, Union, Callable
from .client import BaseClient
from .shared import build_common_params


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

    def __init__(
        self, 
        base_client: BaseClient, 
        aws_access_key_id: str, 
        aws_secret_access_key: str, 
        region_name: str = "us-east-1", 
        aws_session_token: str = None
    ):
        """
        Initialize the videos client.
        
        Args:
            base_client: The base client for API communication
            aws_access_key_id: AWS access key ID (must be passed explicitly)
            aws_secret_access_key: AWS secret access key (must be passed explicitly)
            region_name: AWS region (default 'us-east-1')
            aws_session_token: AWS session token (optional)
        
        Note:
            AWS credentials MUST be passed explicitly. This package does NOT fetch them from the environment.
            The user is responsible for loading credentials from .env or elsewhere and passing them here.
        """
        self._client = base_client
        self._s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name
        )

    def upload_video(
        self,
        device_id: str,
        timestamp: str,
        video_path_or_data: Union[str, bytes],
        content_type: str = 'video/mp4',
        chunk_size: int = 5 * 1024 * 1024,
        max_retries: int = 3,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload a video (from file path or bytes) to S3 using multipart upload, then register it with the backend API.
        Args:
            device_id: Device identifier
            timestamp: ISO-8601 timestamp string
            video_path_or_data: Path to video file or bytes
            content_type: MIME type (default 'video/mp4')
            chunk_size: Multipart chunk size (default 5MB)
            max_retries: Max retries per part
            progress_callback: Optional progress callback (bytes_uploaded, total_bytes, part_number)
            metadata: Optional metadata dict
        Returns:
            Backend API response from registration
        """
        import math
        is_file = isinstance(video_path_or_data, str)
        if is_file:
            if not os.path.exists(video_path_or_data):
                raise FileNotFoundError(f"Video file not found: {video_path_or_data}")
            file_size = os.path.getsize(video_path_or_data)
        else:
            file_size = len(video_path_or_data)
        # S3 key
        formatted_ts = timestamp.replace(':', '-').replace('.', '-').split('+')[0]
        file_extension = self._get_file_extension_from_content_type(content_type)
        s3_key = f"videos/{device_id}/{formatted_ts}{file_extension}"
        # S3 metadata
        s3_metadata = {
            'device_id': device_id,
            'timestamp': timestamp,
            'content_type': content_type
        }
        if metadata:
            s3_metadata['custom_metadata'] = json.dumps(metadata)
        total_parts = math.ceil(file_size / chunk_size)
        bytes_uploaded = 0
        try:
            response = self._s3_client.create_multipart_upload(
                Bucket=self.S3_BUCKET_NAME,
                Key=s3_key,
                ContentType=content_type,
                Metadata={k: str(v) for k, v in s3_metadata.items()}
            )
            upload_id = response['UploadId']
            parts = []
            if is_file:
                with open(video_path_or_data, 'rb') as f:
                    for part_number in range(1, total_parts + 1):
                        part_data = f.read(chunk_size)
                        part_size = len(part_data)
                        self._upload_part(
                            s3_key, upload_id, part_number, part_data, max_retries, bytes_uploaded, file_size, progress_callback, parts
                        )
                        bytes_uploaded += part_size
            else:
                for part_number in range(1, total_parts + 1):
                    start_byte = (part_number - 1) * chunk_size
                    end_byte = min(start_byte + chunk_size, file_size)
                    part_data = video_path_or_data[start_byte:end_byte]
                    part_size = len(part_data)
                    self._upload_part(
                        s3_key, upload_id, part_number, part_data, max_retries, bytes_uploaded, file_size, progress_callback, parts
                    )
                    bytes_uploaded += part_size
            self._s3_client.complete_multipart_upload(
                Bucket=self.S3_BUCKET_NAME,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            raise ClientError(e.response, f"S3 error: {error_code} - {error_message}")
        register_payload = {
            'device_id': device_id,
            'video_key': s3_key,
            'timestamp': timestamp
        }
        if metadata:
            register_payload['metadata'] = metadata
        response = self._client.post("videos/register", register_payload)
        # Recursively unwrap nested response until we get a dict with 'video_key' or 'id'
        def unwrap(data):
            if isinstance(data, dict):
                # If 'data' is present and is a dict, unwrap it
                if 'data' in data and isinstance(data['data'], dict):
                    return unwrap(data['data'])
                # If 'body' is present and is a JSON string, parse and unwrap it
                if 'body' in data and isinstance(data['body'], str):
                    try:
                        body_data = json.loads(data['body'])
                        return unwrap(body_data)
                    except Exception:
                        pass
                # If 'video_key' or 'id' at this level, return
                if 'video_key' in data or 'id' in data:
                    return data
            return data
        return unwrap(response)

    def _upload_part(
        self,
        s3_key: str,
        upload_id: str,
        part_number: int,
        part_data: bytes,
        max_retries: int,
        bytes_uploaded: int,
        total_bytes: int,
        progress_callback: Optional[Callable[[int, int, int], None]],
        parts: list
    ) -> None:
        """
        Upload a part of a multipart upload.
        
        Args:
            s3_key: S3 key of the video
            upload_id: Upload ID of the multipart upload
            part_number: Part number of the upload
            part_data: Data of the part
            max_retries: Max retries per part
            bytes_uploaded: Total bytes uploaded so far
            total_bytes: Total bytes of the video
            progress_callback: Optional progress callback (bytes_uploaded, total_bytes, part_number)
            parts: List of parts uploaded so far
        """
        retry_count = 0
        upload_success = False
        while not upload_success and retry_count <= max_retries:
            try:
                part_response = self._s3_client.upload_part(
                    Bucket=self.S3_BUCKET_NAME,
                    Key=s3_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=part_data
                )
                parts.append({
                    'PartNumber': part_number,
                    'ETag': part_response['ETag']
                })
                upload_success = True
                if progress_callback:
                    progress_callback(bytes_uploaded, total_bytes, part_number)
            except ClientError as e:
                retry_count += 1
                if retry_count > max_retries:
                    raise

    def _get_file_extension_from_content_type(self, content_type: str) -> str:
        """
        Return the file extension for a given MIME content type.
        Defaults to .mp4 if unknown.
        """
        mapping = {
            'video/mp4': '.mp4',
            'video/webm': '.webm',
            'video/quicktime': '.mov',
            'video/x-msvideo': '.avi',
        }
        return mapping.get(content_type, '.mp4')

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
            response = self._client.post("videos/register", register_payload)
            return response
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
