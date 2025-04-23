import os
import pytest
from dotenv import load_dotenv
from sensing_garden_client import SensingGardenClient
import uuid

load_dotenv()

@pytest.fixture(scope="module")
def client():
    api_key = os.getenv("SENSING_GARDEN_API_KEY")
    base_url = os.getenv("API_BASE_URL")
    assert api_key and base_url, "API credentials must be set in .env"
    return SensingGardenClient(base_url=base_url, api_key=api_key)

def random_device_id():
    return f"test-device-{uuid.uuid4().hex[:8]}"

def test_add_and_delete_device(client):
    device_id = random_device_id()
    # Add device
    resp = client.add_device(device_id)
    assert resp["statusCode"] == 200 or resp.get("message", "").lower().startswith("device added"), f"Add failed: {resp}"
    # Fetch device
    items, _ = client.get_devices(device_id=device_id)
    assert any(d["device_id"] == device_id for d in items), f"Device {device_id} not found after add"
    # Delete device
    resp2 = client.delete_device(device_id)
    assert resp2["statusCode"] == 200 or resp2.get("message", "").lower().startswith("device deleted"), f"Delete failed: {resp2}"
    # Ensure device gone
    items2, _ = client.get_devices(device_id=device_id)
    assert not any(d["device_id"] == device_id for d in items2), f"Device {device_id} still present after delete"

def test_add_device_missing_id(client):
    with pytest.raises(Exception):
        client.add_device("")

def test_delete_device_missing_id(client):
    with pytest.raises(Exception):
        client.delete_device("")
