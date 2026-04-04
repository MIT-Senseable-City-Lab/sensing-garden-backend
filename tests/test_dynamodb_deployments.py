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
    def fake_paginate_all(table, method, **kwargs):
        assert method in {"scan", "query"}
        if kwargs.get("ProjectionExpression") == "device_id":
            return [{"device_id": "test-device-json"}, {"device_id": "prod-device-1"}]
        if "test-device-json" in str(kwargs.get("KeyConditionExpression")):
            return [{"device_id": "test-device-json", "timestamp": "20250425_145508"}]
        return [{"device_id": "prod-device-1", "timestamp": "2026-01-15T10:00:00"}]

    monkeypatch.setattr(dynamodb, "_paginate_all", fake_paginate_all)

    items = dynamodb._load_table_items_for_devices(
        dynamodb.CLASSIFICATIONS_TABLE,
        device_ids=None,
        start_time="2025-12-12T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
    )

    assert items == [{"device_id": "prod-device-1", "timestamp": "2026-01-15T10:00:00"}]


def test_load_items_for_query_data_without_device_id_queries_known_devices(monkeypatch):
    class _FakeTable:
        pass

    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(dynamodb, "_list_all_device_ids", lambda: ["device-1", "device-2"])
    monkeypatch.setattr(
        dynamodb,
        "_paginate_all",
        lambda table, method, **kwargs: [{"device_id": "device-1"}] if "device-1" in str(kwargs.get("KeyConditionExpression")) else [{"device_id": "device-2"}],
    )

    items = dynamodb._load_items_for_query_data("classification", device_id=None, model_id=None)

    assert items == [{"device_id": "device-1"}, {"device_id": "device-2"}]


def test_load_table_items_for_device_query_filters_legacy_timestamps_in_memory(monkeypatch):
    class _FakeTable:
        pass

    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(
        dynamodb,
        "_paginate_all",
        lambda table, method, **kwargs: [
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
        "_paginate_all",
        lambda table, method, **kwargs: [
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
        "_paginate_all",
        lambda table, method, **kwargs: [
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


def test_list_tracks_queries_by_device_index(monkeypatch):
    class _FakeTable:
        pass

    captured = []
    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable())
    monkeypatch.setattr(dynamodb, "_list_all_device_ids", lambda: ["device-1", "device-2"])

    def fake_paginate_all(table, method, **kwargs):
        assert method == "query"
        captured.append(kwargs)
        if "device-1" in str(kwargs.get("KeyConditionExpression")):
            return [{"track_id": "track-1", "device_id": "device-1", "timestamp": "2026-03-01T00:00:00"}]
        return [{"track_id": "track-2", "device_id": "device-2", "timestamp": "2026-03-02T00:00:00"}]

    monkeypatch.setattr(dynamodb, "_paginate_all", fake_paginate_all)

    result = dynamodb.list_tracks(
        device_ids=None,
        start_time="2026-03-01T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
        limit=10,
        next_token=None,
        sort_by="timestamp",
        sort_desc=False,
    )

    assert result["count"] == 2
    assert [item["track_id"] for item in result["items"]] == ["track-1", "track-2"]
    assert all(call["IndexName"] == "device_id_index" for call in captured)


def test_count_tracks_filters_legacy_timestamps(monkeypatch):
    monkeypatch.setattr(
        dynamodb,
        "_load_tracks_for_devices",
        lambda device_ids, start_time, end_time: [
            {"track_id": "track-1", "timestamp": "2026-03-01T00:00:00"},
            {"track_id": "track-2", "timestamp": "2026-03-02T00:00:00"},
        ],
    )

    result = dynamodb.count_tracks(
        device_ids=["device-1"],
        start_time="2026-03-01T00:00:00Z",
        end_time="2026-03-31T23:59:59Z",
    )

    assert result == {"count": 2}


def test_get_latest_heartbeats_queries_one_per_device(monkeypatch):
    class _FakeHeartbeatTable:
        def query(self, **kwargs):
            if "device-1" in str(kwargs.get("KeyConditionExpression")):
                return {"Items": [{"device_id": "device-1", "timestamp": "2026-03-02T00:00:00"}]}
            return {"Items": []}

    monkeypatch.setattr(dynamodb, "_list_all_device_ids", lambda: ["device-1", "device-2"])
    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeHeartbeatTable())

    result = dynamodb.get_latest_heartbeats()

    assert result == {
        "items": [{"device_id": "device-1", "timestamp": "2026-03-02T00:00:00"}],
        "count": 1,
    }
