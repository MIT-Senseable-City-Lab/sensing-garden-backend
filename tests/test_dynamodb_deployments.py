from botocore.exceptions import ClientError

import dynamodb


class _FakeTable:
    def __init__(self, error):
        self._error = error

    def put_item(self, **kwargs):
        raise self._error


def test_store_deployment_data_conflict(monkeypatch):
    error = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "exists",
            }
        },
        "PutItem",
    )
    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable(error))

    response = dynamodb.store_deployment_data({"deployment_id": "dep-1", "name": "A"})

    assert response["statusCode"] == 409


def test_store_deployment_device_connection_conflict(monkeypatch):
    error = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "exists",
            }
        },
        "PutItem",
    )
    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable(error))

    response = dynamodb.store_deployment_device_connection_data({
        "deployment_id": "dep-1",
        "device_id": "device-1",
    })

    assert response["statusCode"] == 409


def test_parse_time_supports_legacy_timestamp_format():
    parsed = dynamodb._parse_time("20250425_145508")

    assert parsed is not None
    assert parsed.year == 2025
    assert parsed.month == 4
    assert parsed.day == 25


def test_load_table_items_for_devices_filters_legacy_timestamps_in_memory(monkeypatch):
    class _FakeTable:
        pass

    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(
        dynamodb,
        "_scan_all",
        lambda table, **kwargs: [
            {"device_id": "test-device-json", "timestamp": "20250425_145508"},
            {"device_id": "prod-device-1", "timestamp": "2026-01-15T10:00:00"},
        ],
    )

    items = dynamodb._load_table_items_for_devices(
        dynamodb.CLASSIFICATIONS_TABLE,
        device_ids=None,
        start_time="2025-12-12T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
    )

    assert items == [{"device_id": "prod-device-1", "timestamp": "2026-01-15T10:00:00"}]


def test_load_table_items_for_device_query_filters_legacy_timestamps_in_memory(monkeypatch):
    class _FakeTable:
        pass

    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(
        dynamodb,
        "_query_all",
        lambda table, **kwargs: [
            {"device_id": "device-1", "timestamp": "20250425_145508"},
            {"device_id": "device-1", "timestamp": "2026-02-01T12:00:00"},
        ],
    )

    items = dynamodb._load_table_items_for_devices(
        dynamodb.CLASSIFICATIONS_TABLE,
        device_ids=["device-1"],
        start_time="2025-12-12T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
    )

    assert items == [{"device_id": "device-1", "timestamp": "2026-02-01T12:00:00"}]


def test_query_data_filters_legacy_timestamps_for_detections(monkeypatch):
    class _FakeTable:
        def get_item(self, **kwargs):
            return {}

    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(
        dynamodb,
        "_query_all",
        lambda table, **kwargs: [
            {"device_id": "device-1", "timestamp": "20250425_145508"},
            {"device_id": "device-1", "timestamp": "2026-02-01T12:00:00", "model_id": "model-1"},
        ],
    )

    result = dynamodb.query_data(
        "detection",
        device_id="device-1",
        model_id="model-1",
        start_time="2025-12-12T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
        limit=50,
    )

    assert result["items"] == [{"device_id": "device-1", "timestamp": "2026-02-01T12:00:00", "model_id": "model-1"}]
    assert result["count"] == 1


def test_count_data_filters_legacy_timestamps_for_videos(monkeypatch):
    class _FakeTable:
        def get_item(self, **kwargs):
            return {}

    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(
        dynamodb,
        "_query_all",
        lambda table, **kwargs: [
            {"device_id": "device-1", "timestamp": "20250425_145508"},
            {"device_id": "device-1", "timestamp": "2026-02-01T12:00:00"},
        ],
    )

    result = dynamodb.count_data(
        "video",
        device_id="device-1",
        start_time="2025-12-12T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
    )

    assert result == {"count": 1}
