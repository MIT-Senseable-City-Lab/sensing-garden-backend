"""
Example usage of the new sensing_garden_client API structure.

This script demonstrates how to use the new object-oriented API client.
"""
import os
from datetime import datetime

import requests

import sensing_garden_client

# Load API credentials from environment variables
api_key = os.environ.get("SENSING_GARDEN_API_KEY")
api_base_url = os.environ.get("API_BASE_URL")

# Initialize the client
sgc = sensing_garden_client.SensingGardenClient(api_base_url, api_key)

# Examples of using the models client
print("=== Models API ===")
try:
    # Create a model
    model_result = sgc.models.create(
        model_id="example-model-123",
        name="Example Model",
        version="1.0.0",
        description="A model created using the new client API"
    )
    print(f"Created model: {model_result}")
    
    # Fetch models
    models = sgc.models.fetch(limit=5)
    print(f"Retrieved {len(models.get('items', []))} models")
except Exception as e:
    print(f"Error with models API: {str(e)}")

# Examples of using the detections client (commented out as it requires image data)
print("\n=== Detections API ===")
"""
# To use this example, uncomment and provide actual image data
with open("example_image.jpg", "rb") as f:
    image_data = f.read()

# Add a detection
detection_result = sgc.detections.add(
    device_id="device-123",
    model_id="example-model-123",
    image_data=image_data,
    bounding_box=[0.1, 0.2, 0.3, 0.4],
    timestamp=datetime.utcnow().isoformat()
)
print(f"Created detection: {detection_result}")
"""

# Fetch detections
try:
    detections = sgc.detections.fetch(limit=5)
    print(f"Retrieved {len(detections.get('items', []))} detections")
except Exception as e:
    print(f"Error with detections API: {str(e)}")

# Examples of using the classifications client (commented out as it requires image data)
print("\n=== Classifications API ===")
"""
# To use this example, uncomment and provide actual image data
with open("example_image.jpg", "rb") as f:
    image_data = f.read()

# Add a classification
classification_result = sgc.classifications.add(
    device_id="device-123",
    model_id="example-model-123",
    image_data=image_data,
    family="Rosaceae",
    genus="Rosa",
    species="Rosa gallica",
    family_confidence=0.95,
    genus_confidence=0.92,
    species_confidence=0.85,
    timestamp=datetime.utcnow().isoformat()
)
print(f"Created classification: {classification_result}")
"""

# Fetch classifications
try:
    classifications = sgc.classifications.fetch(limit=5)
    print(f"Retrieved {len(classifications.get('items', []))} classifications")
except Exception as e:
    print(f"Error with classifications API: {str(e)}")

# Examples of using the videos client (new API)
print("\n=== Videos API ===")

from sensing_garden_client.videos import VideosClient

# Load AWS credentials from environment variables
aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
aws_region = os.environ.get("AWS_REGION", "us-east-1")
aws_session_token = os.environ.get("AWS_SESSION_TOKEN")

# Initialize the videos client (explicit credentials)
videos_client = VideosClient(
    base_client=sgc._base_client,  # Use the base client from the main SensingGardenClient
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region,
    aws_session_token=aws_session_token
)

# Example 1: Upload by file path
video_path = os.path.join(os.path.dirname(__file__), "../../tests/data/sample_video.mp4")
result = videos_client.upload_video(
    device_id="device-123",
    timestamp=datetime.utcnow().isoformat(),
    video_path_or_data=video_path,
    content_type="video/mp4",
    metadata={"location": "greenhouse-A", "duration_seconds": 120}
)
print(f"Uploaded video from file: {result}")

# Example 2: Upload by bytes
with open(video_path, "rb") as f:
    video_bytes = f.read()
result2 = videos_client.upload_video(
    device_id="device-123",
    timestamp=datetime.utcnow().isoformat(),
    video_path_or_data=video_bytes,
    content_type="video/mp4",
    metadata={"location": "greenhouse-A", "duration_seconds": 120, "source": "bytes"}
)
print(f"Uploaded video from bytes: {result2}")

# Fetch videos
try:
    # Fetch videos for a specific device with time range filtering
    start_time = datetime(2025, 1, 1).isoformat()
    end_time = datetime.utcnow().isoformat()
    
    videos = sgc.videos.fetch(
        device_id="device-123",
        start_time=start_time,
        end_time=end_time,
        limit=5
    )
    print(f"Retrieved {len(videos.get('items', []))} videos")
    
    if videos.get('items') and len(videos['items']) > 0:
        print(f"First video URL: {videos['items'][0].get('url')}")
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
        print("Videos API endpoint is not available yet. The API Gateway needs to be updated with the video routes.")
        print("To fix this, deploy the API Gateway with the video endpoint routes added to the configuration.")
    else:
        print(f"HTTP error with videos API: {str(e)}")
except Exception as e:
    print(f"Error with videos API: {str(e)}")
