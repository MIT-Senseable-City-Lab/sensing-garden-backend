#!/usr/bin/env python3
"""
Tests for the Sensing Garden API video endpoints.
This module tests both uploading and retrieving videos.
"""
import argparse
import os
import sys
import tempfile
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

import requests

from test_utils import (
    DEFAULT_TEST_DEVICE_ID,
    get_client,
    create_test_video,
    print_response
)

def test_upload_video(
    device_id: str,
    timestamp: Optional[str] = None,
    video_file_path: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Test uploading a video to the Sensing Garden API.
    
    Args:
        device_id: Device ID to use for testing
        timestamp: Optional timestamp to use (defaults to current time)
        video_file_path: Optional path to a video file to upload
        
    Returns:
        Tuple of (success, timestamp)
    """
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = timestamp or datetime.now().isoformat()
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting VIDEO UPLOAD with device_id: {device_id}")
    
    try:
        # If a video file path is provided and exists, use the upload_file method
        if video_file_path and os.path.exists(video_file_path):
            print(f"Using video file: {video_file_path}")
            # Determine file size for logging
            file_size = os.path.getsize(video_file_path)
            print(f"Video file size: {file_size / (1024 * 1024):.2f} MB")
            
            # Use the upload_file method to upload the video
            response_data = client.videos.upload_file(
                device_id=device_id,
                video_file_path=video_file_path,
                description=f"Test video upload at {request_timestamp}",
                timestamp=request_timestamp,
                metadata={"test": True, "source": "test_videos.py"}
            )
        else:
            # If no file is provided, use the generated test data with standard upload
            print("No valid video file provided, using generated test data")
            video_data = create_test_video()
            
            # For small test videos, we can use the upload_file method
            # Create a temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_file.write(video_data)
                temp_file_path = temp_file.name
            
            try:
                # Use the upload_file method with the temporary file
                response_data = client.videos.upload_file(
                    device_id=device_id,
                    video_file_path=temp_file_path,
                    description=f"Test video upload at {request_timestamp}",
                    timestamp=request_timestamp,
                    metadata={"test": True, "source": "test_videos.py"}
                )
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        
        print_response(response_data)
        print(f"\n✅ Video upload successful!")
        success = True
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Video upload failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    
    return success, request_timestamp

def test_fetch_videos(
    device_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Test retrieving videos from the Sensing Garden API.
    
    Args:
        device_id: Device ID to filter by
        start_time: Optional start time for filtering (ISO-8601)
        end_time: Optional end time for filtering (ISO-8601)
        sort_by: Optional attribute to sort by
        sort_desc: Whether to sort in descending order
        
    Returns:
        Tuple of (success, response data)
    """
    if not start_time:
        # If no specific start_time provided, use a time range from beginning of 2023
        start_time = datetime(2023, 1, 1).isoformat()
    
    if not end_time:
        # If no specific end_time provided, use current time
        end_time = datetime.now().isoformat()
    
    # Get the client
    client = get_client()
    
    print(f"\n\nTesting VIDEO FETCH with device_id: {device_id}")
    print(f"Searching from {start_time} to {end_time}")
    
    try:
        # Use the videos.fetch method to get videos for the device
        data = client.videos.fetch(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=10,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        # Check if we got any results
        if data.get('items') and len(data['items']) > 0:
            print(f"✅ Video fetch successful! Found {len(data['items'])} videos.")
            
            # Print details of each video
            for i, video in enumerate(data['items']):
                print(f"\nVideo {i+1}:")
                print(f"  Device ID: {video.get('device_id')}")
                print(f"  Timestamp: {video.get('timestamp')}")
                print(f"  Description: {video.get('description')}")
                print(f"  Video URL: {video.get('video_url', 'No URL available')}")
                
                # Print metadata if available
                if 'metadata' in video:
                    print(f"  Metadata: {video.get('metadata')}")
            
            return True, data
        else:
            print(f"❌ No videos found for device {device_id} in the specified time range.")
            return False, data
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Video fetch request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return False, None
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, None

def add_test_videos(device_id: str, num_videos: int = 3) -> bool:
    """
    Add test videos for a device.
    
    Args:
        device_id: Device ID to use
        num_videos: Number of videos to add
        
    Returns:
        bool: Whether all videos were added successfully
    """
    print(f"\nAdding {num_videos} test videos for device {device_id}")
    
    # Get the sample video paths
    sample_video_path = os.path.join(os.path.dirname(__file__), 'data', 'sample_video.mp4')
    large_video_path = os.path.join(os.path.dirname(__file__), 'data', 'file_example_MP4_1280_10MG.mp4')
    
    # Alternate between the two sample videos
    video_paths = [sample_video_path, large_video_path] * ((num_videos + 1) // 2)
    
    success = True
    for i in range(num_videos):
        upload_success, _ = test_upload_video(
            device_id=device_id,
            timestamp=datetime.now().isoformat(),
            video_file_path=video_paths[i % len(video_paths)]
        )
        success = success and upload_success
    
    return success

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API video endpoints')
    parser.add_argument('--device-id', type=str, default=DEFAULT_TEST_DEVICE_ID,
                      help=f'Device ID to use for testing (default: {DEFAULT_TEST_DEVICE_ID})')
    parser.add_argument('--video-file', type=str, 
                      default=os.path.join(os.path.dirname(__file__), 'data', 'sample_video.mp4'),
                      help='Path to a video file for upload testing')
    parser.add_argument('--timestamp', type=str, help='Optional timestamp to use for testing')
    parser.add_argument('--upload', action='store_true', help='Test video upload')
    parser.add_argument('--fetch', action='store_true', help='Test video fetch')
    parser.add_argument('--add-test-data', action='store_true', help='Add test videos')
    parser.add_argument('--num-videos', type=int, default=3, help='Number of test videos to add')
    
    args = parser.parse_args()
    
    # Use provided timestamp or generate a new one
    timestamp = args.timestamp or datetime.now().isoformat()
    
    # Run the appropriate tests
    success = True
    
    # Default to running both upload and fetch if neither is specified
    run_upload = args.upload or (not args.upload and not args.fetch)
    run_fetch = args.fetch or (not args.upload and not args.fetch)
    
    # Test video upload
    if run_upload:
        upload_success, _ = test_upload_video(args.device_id, timestamp, args.video_file)
        success &= upload_success
    
    # Add test data if requested
    if args.add_test_data:
        add_success = add_test_videos(args.device_id, args.num_videos)
        success &= add_success
    
    # Test video fetch
    if run_fetch:
        fetch_success, _ = test_fetch_videos(args.device_id)
        success &= fetch_success
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
