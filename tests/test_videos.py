#!/usr/bin/env python3
"""
Test for video upload functionality in the Sensing Garden Client.
"""
import os
from datetime import datetime
import os
from datetime import datetime
import pytest
from .test_utils import get_client

VIDEO_DIR = os.path.join(os.path.dirname(__file__), "data")
VIDEO_FILES = [
    f for f in os.listdir(VIDEO_DIR)
    if f.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))
]

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

@pytest.mark.skipif(
    not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
    reason="AWS credentials not set in environment"
)
def test_video_upload(device_id):
    client = get_client()
    errors = 0
    for video_file in VIDEO_FILES:
        video_path = os.path.join(VIDEO_DIR, video_file)
        timestamp = datetime.now().isoformat()
        try:
            response = client.videos.upload_video(
                device_id=device_id,
                timestamp=timestamp,
                video_path_or_data=video_path,
                content_type="video/mp4"
            )
            assert response and isinstance(response, dict), f"No or invalid response for {video_file}: {response}"
            assert ("video_key" in response or "id" in response), f"No video_key/id in response for {video_file}: {response}"
            print(f"[PASS] Uploaded {video_file}: {response}")
        except Exception as e:
            # Print full error details for debugging
            import traceback
            traceback.print_exc()
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print(f"[ERROR] API response: {e.response.text}")
            else:
                print(f"[ERROR] Exception uploading {video_file}: {e}")
            errors += 1
    assert errors == 0, f"{errors} video uploads failed. See output above."
