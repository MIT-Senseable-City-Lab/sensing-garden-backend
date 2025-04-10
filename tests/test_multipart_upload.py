#!/usr/bin/env python3
"""
Test script for multipart video uploads to the Sensing Garden API.

This script tests the multipart upload functionality by uploading a video file
to the Sensing Garden API using the client's multipart upload feature.
It demonstrates progress tracking and error handling for large file uploads.
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime

from sensing_garden_client import SensingGardenClient


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Test multipart video uploads to the Sensing Garden API')
    parser.add_argument('--device-id', type=str, required=True,
                        help='Device ID to use for the upload')
    parser.add_argument('--video-file', type=str, required=True,
                        help='Path to the video file to upload')
    parser.add_argument('--chunk-size', type=int, default=5 * 1024 * 1024,
                        help='Chunk size in bytes for multipart upload (default: 5MB)')
    parser.add_argument('--max-retries', type=int, default=3,
                        help='Maximum number of retry attempts for failed uploads (default: 3)')
    parser.add_argument('--no-progress', action='store_true',
                        help='Disable progress display during upload')
    return parser.parse_args()


def progress_callback(bytes_uploaded, total_bytes, part_number):
    """Display upload progress."""
    percent = (bytes_uploaded / total_bytes) * 100
    mb_uploaded = bytes_uploaded / (1024 * 1024)
    total_mb = total_bytes / (1024 * 1024)
    
    # Clear the current line and print progress
    print(f"\rUploading part {part_number}: {mb_uploaded:.2f} MB / {total_mb:.2f} MB ({percent:.1f}%)", end="")
    
    # If upload is complete, print a newline
    if bytes_uploaded == total_bytes:
        print()


def main():
    """Main entry point for the test script."""
    args = parse_args()
    
    # Validate the video file exists
    if not os.path.exists(args.video_file):
        print(f"Error: Video file '{args.video_file}' does not exist")
        return 1
    
    # Get file size for logging
    file_size = os.path.getsize(args.video_file)
    print(f"Video file size: {file_size / (1024 * 1024):.2f} MB")
    
    # Initialize the client with API key and base URL from environment
    api_key = os.environ.get('SENSING_GARDEN_API_KEY')
    if not api_key:
        print("Error: SENSING_GARDEN_API_KEY environment variable is not set")
        return 1
    
    api_base_url = os.environ.get('API_BASE_URL')
    if not api_base_url:
        print("Error: API_BASE_URL environment variable is not set")
        return 1
    
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    
    # Create a unique timestamp for this request
    timestamp = datetime.now().isoformat()
    
    print(f"\nTesting multipart video upload with:")
    print(f"  Device ID: {args.device_id}")
    print(f"  Video file: {args.video_file}")
    print(f"  Chunk size: {args.chunk_size / (1024 * 1024):.2f} MB")
    print(f"  Max retries: {args.max_retries}")
    print(f"  Progress display: {'Disabled' if args.no_progress else 'Enabled'}")
    print(f"  API Base URL: {api_base_url}")
    
    # Set up progress callback if enabled
    callback = None if args.no_progress else progress_callback
    
    start_time = time.time()
    
    try:
        # Use the upload_file method which handles multipart uploads automatically
        print("\nStarting multipart upload...")
        response_data = client.videos.upload_file(
            device_id=args.device_id,
            video_file_path=args.video_file,
            description=f"Multipart test upload at {timestamp}",
            timestamp=timestamp,
            metadata={"test": True, "source": "test_multipart_upload.py"},
            chunk_size=args.chunk_size,
            max_retries=args.max_retries,
            progress_callback=callback
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\nMultipart upload completed in {duration:.2f} seconds")
        print(f"Response: {json.dumps(response_data, indent=2)}")
        print(f"\n✅ Multipart video upload successful!")
        
        # Print the video URL if available
        if "video_url" in response_data:
            print(f"Video URL: {response_data['video_url']}")
        
        # Calculate and display upload speed
        upload_speed_mbps = (file_size / 1024 / 1024) / duration
        print(f"Average upload speed: {upload_speed_mbps:.2f} MB/s")
        
        return 0
            
    except Exception as e:
        print(f"\n❌ Multipart upload failed: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
