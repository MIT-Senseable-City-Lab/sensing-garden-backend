#!/usr/bin/env python3
"""
Test script for S3 multipart upload functionality in the Sensing Garden client.

This script tests the direct S3 multipart upload functionality in the Sensing Garden client,
which uses S3's native multipart upload capabilities instead of a custom API and DynamoDB.
"""
import os
import sys
import time
import argparse
import boto3
from datetime import datetime
from typing import Dict, Any, Optional

# Add the parent directory to the path so we can import the client
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the client
from sensing_garden_client import SensingGardenClient

def print_progress(bytes_uploaded: int, total_bytes: int, part_number: int) -> None:
    """Print upload progress."""
    percentage = (bytes_uploaded / total_bytes) * 100
    print(f"\rUploaded {bytes_uploaded}/{total_bytes} bytes ({percentage:.2f}%) - Part {part_number}", end="")

def main():
    """Main function to test S3 multipart upload."""
    parser = argparse.ArgumentParser(description="Test S3 multipart upload functionality")
    parser.add_argument("--video", type=str, default="tests/data/sample_video.mp4",
                        help="Path to video file to upload")
    parser.add_argument("--device-id", type=str, default="test-device-1",
                        help="Device ID to use for the upload")
    parser.add_argument("--chunk-size", type=int, default=5,
                        help="Chunk size in MB for multipart upload")
    parser.add_argument("--api-key", type=str, 
                        help="API key for authentication (defaults to SENSING_GARDEN_API_KEY env var)")
    parser.add_argument("--api-url", type=str, 
                        help="Base URL for the API (defaults to API_BASE_URL env var)")
    parser.add_argument("--aws-access-key", type=str,
                        help="AWS access key for S3 access (defaults to AWS_ACCESS_KEY_ID env var)")
    parser.add_argument("--aws-secret-key", type=str,
                        help="AWS secret key for S3 access (defaults to AWS_SECRET_ACCESS_KEY env var)")
    parser.add_argument("--aws-region", type=str, default="us-east-1",
                        help="AWS region for S3 access (defaults to us-east-1)")
    args = parser.parse_args()

    # Get API key and base URL from environment variables if not provided
    api_key = args.api_key or os.environ.get("SENSING_GARDEN_API_KEY")
    api_base_url = args.api_url or os.environ.get("API_BASE_URL")
    
    # Get AWS credentials from environment variables if not provided
    aws_access_key = args.aws_access_key or os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = args.aws_secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = args.aws_region or os.environ.get("AWS_REGION", "us-east-1")

    if not api_key:
        print("Error: API key not provided. Use --api-key or set SENSING_GARDEN_API_KEY environment variable.")
        return 1

    if not api_base_url:
        print("Error: API base URL not provided. Use --api-url or set API_BASE_URL environment variable.")
        return 1

    # Check if AWS credentials are provided
    if not aws_access_key or not aws_secret_key:
        print("Warning: AWS credentials not provided. S3 operations may fail.")
        print("Use --aws-access-key and --aws-secret-key or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.")

    # Check if video file exists
    if not os.path.exists(args.video):
        print(f"Error: Video file not found: {args.video}")
        return 1

    # Configure boto3 with AWS credentials if provided
    if aws_access_key and aws_secret_key:
        boto3.setup_default_session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )

    # Initialize client
    client = SensingGardenClient(base_url=api_base_url, api_key=api_key)
    videos_client = client.videos

    # Get file size
    file_size = os.path.getsize(args.video)
    print(f"Video file: {args.video}")
    print(f"File size: {file_size} bytes ({file_size / (1024 * 1024):.2f} MB)")
    print(f"Device ID: {args.device_id}")
    print(f"Chunk size: {args.chunk_size} MB")
    print(f"API base URL: {api_base_url}")
    print("Starting upload...")

    # Start timer
    start_time = time.time()

    try:
        # Upload video using multipart upload
        result = videos_client.upload_file(
            device_id=args.device_id,
            video_file_path=args.video,
            description=f"Test video upload at {datetime.now().isoformat()}",
            chunk_size=args.chunk_size * 1024 * 1024,  # Convert MB to bytes
            progress_callback=print_progress
        )

        # End timer
        end_time = time.time()
        duration = end_time - start_time

        print("\nUpload completed successfully!")
        print(f"Upload took {duration:.2f} seconds")
        print(f"Average upload speed: {file_size / duration / 1024 / 1024:.2f} MB/s")
        print(f"Result: {result}")

        return 0

    except Exception as e:
        print(f"\nError during upload: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
