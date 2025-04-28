#!/usr/bin/env python3
"""
Test for video upload functionality in the Sensing Garden Client.
"""
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
@pytest.mark.skipif(
    not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
    reason="AWS credentials not set in environment"
)
def test_video_upload():
    """
    Upload a single video from tests/data for device_id 'test-device-2025'.
    """
    client = get_client()
    device_id = "test-device-2025"
    video_file = VIDEO_FILES[0]
    video_path = os.path.join(VIDEO_DIR, video_file)
    timestamp = datetime.now().isoformat()
    response = client.videos.upload_video(
        device_id=device_id,
        timestamp=timestamp,
        video_path_or_data=video_path,
        content_type="video/mp4"
    )
    assert response and isinstance(response, dict), f"No or invalid response for {video_file}: {response}"
    assert ("video_key" in response or "id" in response), f"No video_key/id in response for {video_file}: {response}"
    print(f"[PASS] Uploaded {video_file}: {response}")

@pytest.mark.skipif(
    not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
    reason="AWS credentials not set in environment"
)
def test_upload_all_videos_for_2025():
    """
    Upload all videos in tests/data for device_id 'test-device-2025'.
    """
    client = get_client()
    device_id = "test-device-2025"
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
            import traceback
            traceback.print_exc()
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print(f"[ERROR] API response: {e.response.text}")
            else:
                print(f"[ERROR] Exception uploading {video_file}: {e}")
            errors += 1
    assert errors == 0, f"{errors} video uploads failed. See output above."

@pytest.mark.skipif(
    not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
    reason="AWS credentials not set in environment"
)
def test_videos_pagination_desc_order():
    """
    Fetch videos in descending order (by timestamp) and verify that the first video on the second page
    is older than the last video on the first page. Prints all timestamps for inspection.
    """
    client = get_client()
    device_id = "test-device-2025"
    # Fetch first page
    page1 = client.videos.fetch(device_id=device_id, limit=5, sort_by="timestamp", sort_desc=True)
    items1 = page1.get("items", [])
    next_token = page1.get("next_token")
    assert len(items1) > 0, "No videos found on first page"
    assert next_token, "No next_token for pagination"

    # Fetch second page
    page2 = client.videos.fetch(device_id=device_id, limit=5, sort_by="timestamp", sort_desc=True, next_token=next_token)
    items2 = page2.get("items", [])
    assert len(items2) > 0, "No videos found on second page"

    # Print all timestamps for inspection
    print("\nFirst page timestamps:")
    for i, v in enumerate(items1):
        print(f"  {i}: {v['timestamp']}")
    print("Second page timestamps:")
    for i, v in enumerate(items2):
        print(f"  {i}: {v['timestamp']}")

    # Parse all timestamps and normalize to UTC, offset-naive
    from dateutil.parser import isoparse
    from datetime import timezone
    def to_naive_utc(ts):
        dt = isoparse(ts)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    t1 = [to_naive_utc(v['timestamp']) for v in items1]
    t2 = [to_naive_utc(v['timestamp']) for v in items2]

    # Assert every item on page 1 is newer than every item on page 2
    errors = []
    for i, t1i in enumerate(t1):
        for j, t2j in enumerate(t2):
            if t1i <= t2j:
                errors.append((i, j, t1i, t2j))
    if errors:
        print("Pagination order errors:")
        for i, j, t1i, t2j in errors:
            print(f"  Page1[{i}] ({t1i}) is not newer than Page2[{j}] ({t2j})")
    assert not errors, "Expected all videos on first page to be newer than all on second page. See printout for violations."
