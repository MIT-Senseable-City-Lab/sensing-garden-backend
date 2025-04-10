#!/usr/bin/env python3
import argparse
import io
import json
import os
import random
import string
import sys
import uuid
from datetime import datetime
from decimal import Decimal
import tempfile

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw
# Import the Sensing Garden client package
from sensing_garden_client import SensingGardenClient

# Load environment variables
load_dotenv()

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Create a test video (simulated with a small binary file)
def create_test_video():
    """Create a simple binary file that simulates a video"""
    # In a real scenario, this would be actual video data
    video_data = bytearray([random.randint(0, 255) for _ in range(1024)])
    return bytes(video_data)

def test_post_video(device_id, timestamp, video_file_path=None):
    """Test the video API POST endpoint"""
    # Create a unique timestamp for this request to avoid DynamoDB key conflicts
    request_timestamp = datetime.now().isoformat()
    
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        raise ValueError("SENSING_GARDEN_API_KEY environment variable is not set")
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    # Set AWS credentials for S3 access
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    if not aws_access_key or not aws_secret_key:
        print("Warning: AWS credentials not set. S3 operations may fail.")
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
    print(f"\n\nTesting VIDEO POST with device_id: {device_id}")
    
    try:
        # If a video file path is provided and exists, use the upload_file method
        if video_file_path and os.path.exists(video_file_path):
            print(f"Using video file: {video_file_path} with direct S3 multipart upload")
            # Determine file size for logging
            file_size = os.path.getsize(video_file_path)
            print(f"Video file size: {file_size / (1024 * 1024):.2f} MB")
            
            # Use the upload_file method which handles S3 multipart uploads directly
            response_data = client.videos.upload_file(
                device_id=device_id,
                video_file_path=video_file_path,
                description=f"Test video upload at {request_timestamp}",
                timestamp=request_timestamp,
                metadata={"test": True, "source": "test_video_api.py"}
            )
        else:
            # If no file is provided, use the generated test data with standard upload
            print("No valid video file provided, using generated test data")
            video_data = create_test_video()
            
            # For small test videos, we can still use the direct upload method
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
                    metadata={"test": True, "source": "test_video_api.py"}
                )
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        
        print(f"Response body: {json.dumps(response_data, indent=2)}")
        print(f"\n✅ Video API upload request successful!")
        success = True
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Video API request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        success = False
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        success = False
    
    return success, request_timestamp

def test_get_videos(device_id, start_time=None, end_time=None, sort_by=None, sort_desc=False):
    """Test the video API GET endpoint"""
    if not start_time:
        # If no specific start_time provided, use a time range from beginning of 2023
        start_time = datetime(2023, 1, 1).isoformat()
    
    if not end_time:
        # If no specific end_time provided, use current time
        end_time = datetime.now().isoformat()
    
    # Initialize the client with API base URL from environment
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        raise ValueError("API_BASE_URL environment variable is not set")
    
    client = SensingGardenClient(base_url=api_base_url)
    
    print(f"\n\nTesting VIDEO GET with device_id: {device_id}")
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
            print(f"✅ Video GET successful! Found {len(data['items'])} videos.")
            
            # Print details of each video
            for i, video in enumerate(data['items']):
                print(f"\nVideo {i+1}:")
                print(f"  Device ID: {video.get('device_id')}")
                print(f"  Timestamp: {video.get('timestamp')}")
                print(f"  Description: {video.get('description')}")
                print(f"  Video URL: {video.get('video_url', 'No URL available')}")
                
                # Print metadata if available
                if 'metadata' in video:
                    print(f"  Metadata: {json.dumps(video.get('metadata'), cls=DecimalEncoder)}")
            
            return True, data
        else:
            print(f"❌ No videos found for device {device_id} in the specified time range.")
            return False, data
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Video GET request failed: {str(e)}")
        print(f"Response status code: {getattr(e.response, 'status_code', 'N/A')}")
        print(f"Response body: {getattr(e.response, 'text', 'N/A')}")
        return False, None
    except Exception as e:
        print(f"❌ Error in test: {str(e)}")
        return False, None

def add_test_videos(device_id, num_videos=3):
    """Add test videos for a device"""
    print(f"\nAdding {num_videos} test videos for device {device_id}")
    
    for i in range(num_videos):
        test_post_video(device_id, datetime.now().isoformat())

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the Sensing Garden API video endpoints')
    parser.add_argument('--device-id', type=str, required=True, help='Device ID to use for testing')
    parser.add_argument('--video-file', type=str, help='Path to a video file for upload testing')
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
        upload_success, _ = test_post_video(args.device_id, timestamp, args.video_file)
        success &= upload_success
    
    # Add test data if requested
    if args.add_test_data:
        add_test_videos(args.device_id, args.num_videos)
    
    # Test video fetch
    if run_fetch:
        fetch_success, _ = test_get_videos(args.device_id)
        success &= fetch_success
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
