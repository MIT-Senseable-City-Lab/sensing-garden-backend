import pytest

# Centralized test variables for all Sensing Garden API tests

test_vars = {
    "device_id": "test-device-2025",
    "model_id": "test-model-2025",
    "nonexistent_model_id": "nonexistent-model-9999",
    "timestamp": "2025-04-15T19:00:55-04:00",
    "video_file_path": "tests/assets/test_video.mp4",
    "endpoint_type": "detection",  # Can be parameterized in tests
    "sort_by": "timestamp",
    "sort_desc": False,
    "hours": 24,
    "start_time": "2025-04-15T00:00:00-04:00",
    "end_time": "2025-04-16T00:00:00-04:00"
}

@pytest.fixture
def device_id():
    return test_vars["device_id"]

@pytest.fixture
def model_id():
    return test_vars["model_id"]

@pytest.fixture
def nonexistent_model_id():
    return test_vars["nonexistent_model_id"]

@pytest.fixture
def timestamp():
    return test_vars["timestamp"]

@pytest.fixture
def video_file_path():
    return test_vars["video_file_path"]

@pytest.fixture
def endpoint_type():
    return test_vars["endpoint_type"]

@pytest.fixture
def client():
    from tests.test_utils import get_client
    return get_client()

@pytest.fixture
def sort_by():
    return test_vars["sort_by"]

@pytest.fixture
def sort_desc():
    return test_vars["sort_desc"]


@pytest.fixture
def start_time():
    return test_vars["start_time"]

@pytest.fixture
def end_time():
    return test_vars["end_time"]
