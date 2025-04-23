import pytest
import uuid
from sensing_garden_client import SensingGardenClient
import os
from dotenv import load_dotenv

load_dotenv()

def random_device_id():
    return f"autopop-test-device-{uuid.uuid4().hex[:8]}"

def get_client():
    api_key = os.getenv("SENSING_GARDEN_API_KEY")
    base_url = os.getenv("API_BASE_URL")
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    aws_session_token = os.getenv("AWS_SESSION_TOKEN")
    assert api_key and base_url, "API credentials must be set in .env"
    return SensingGardenClient(
        base_url=base_url,
        api_key=api_key,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_region=aws_region,
        aws_session_token=aws_session_token
    )

# Helper to check device exists
def device_exists(client, device_id):
    items, _ = client.get_devices(device_id=device_id)
    return any(d["device_id"] == device_id for d in items)

# Helper to clean up device
def cleanup_device(client, device_id):
    client.delete_device(device_id)

# Use a valid model_id for test classification/detection
@pytest.fixture(scope="module")
def valid_model_id():
    client = get_client()
    models_resp = client.models.fetch()
    models = models_resp.get("items") if isinstance(models_resp, dict) else models_resp
    if not models:
        pytest.skip("No models available for test")
    return models[0]["id"]

@pytest.mark.parametrize("data_type", ["video", "classification", "detection"])
def test_device_autopopulation(data_type, valid_model_id):
    client = get_client()
    device_id = random_device_id()
    try:
        if data_type == "video":
            # Use a small fake video (simulate, not upload real file)
            video_data = b"00" * 1024
            resp = client.videos.upload_video(
                device_id=device_id,
                timestamp="2025-04-23T16:20:37-04:00",
                video_path_or_data=video_data,
                content_type="video/mp4"
            )
            assert resp and ("video_key" in resp or "id" in resp), f"Video upload failed: {resp}"
        elif data_type == "classification":
            # Use a small fake image
            image_data = b"00" * 1024
            resp = client.classifications.add(
                device_id=device_id,
                model_id=valid_model_id,
                image_data=image_data,
                family="test_family",
                genus="test_genus",
                species="test_species",
                family_confidence=0.9,
                genus_confidence=0.9,
                species_confidence=0.9,
                timestamp="2025-04-23T16:20:37-04:00"
            )
            assert resp and resp.get("statusCode", 200) == 200, f"Classification upload failed: {resp}"
        elif data_type == "detection":
            image_data = b"00" * 1024
            resp = client.detections.add(
                device_id=device_id,
                model_id=valid_model_id,
                image_data=image_data,
                bounding_box=[0.1, 0.1, 0.5, 0.5],
                timestamp="2025-04-23T16:20:37-04:00"
            )
            assert resp and resp.get("statusCode", 200) == 200, f"Detection upload failed: {resp}"
        else:
            pytest.fail(f"Unknown data_type: {data_type}")
        # Check device autopopulated
        assert device_exists(client, device_id), f"Device {device_id} not autopopulated after {data_type} add"
    finally:
        # Clean up device
        cleanup_device(client, device_id)
        assert not device_exists(client, device_id), f"Device {device_id} not deleted during cleanup"
