import json

import handler


def _http_event(method, path, body=None, query=None, headers=None, raw_query=None):
    event = {
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
            }
        }
    }
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body)
    if query is not None:
        event["queryStringParameters"] = query
    if headers is not None:
        event["headers"] = headers
    if raw_query is not None:
        event["rawQueryString"] = raw_query
    return event


def _set_api_keys(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "admin-key")
    monkeypatch.setenv("FRONTEND_API_KEY", "frontend-key")
    monkeypatch.setenv("DEPLOYMENTS_API_KEY", "deployments-key")
    monkeypatch.delenv("EDGE_API_KEY", raising=False)


def test_validate_api_key_accepts_configured_key_case_insensitive(monkeypatch):
    _set_api_keys(monkeypatch)

    ok, message = handler.validate_api_key({"headers": {"X-Api-Key": "admin-key"}})

    assert ok is True
    assert message == ""


def test_get_routes_require_api_key(monkeypatch):
    _set_api_keys(monkeypatch)

    response = handler.handler(_http_event("GET", "/devices"), None)

    assert response["statusCode"] == 401


def test_deployments_key_can_read_allowed_route(monkeypatch):
    _set_api_keys(monkeypatch)
    monkeypatch.setattr(handler, "handle_get_classifications", lambda event: {"statusCode": 200, "body": "ok"})

    response = handler.handler(
        _http_event("GET", "/classifications", headers={"x-api-key": "deployments-key"}),
        None,
    )

    assert response["statusCode"] == 200


def test_frontend_key_is_read_only(monkeypatch):
    _set_api_keys(monkeypatch)
    monkeypatch.setattr(handler, "handle_get_classifications", lambda event: {"statusCode": 200, "body": "ok"})

    get_response = handler.handler(
        _http_event("GET", "/classifications", headers={"x-api-key": "frontend-key"}),
        None,
    )
    post_response = handler.handler(
        _http_event(
            "POST",
            "/devices",
            body={"device_id": "device-1"},
            headers={"x-api-key": "frontend-key"},
        ),
        None,
    )

    assert get_response["statusCode"] == 200
    assert post_response["statusCode"] == 403


def test_deployments_key_cannot_write_devices(monkeypatch):
    _set_api_keys(monkeypatch)

    response = handler.handler(
        _http_event(
            "POST",
            "/devices",
            body={"device_id": "device-1"},
            headers={"x-api-key": "deployments-key"},
        ),
        None,
    )

    assert response["statusCode"] == 403


def test_deployments_key_can_manage_deployments(monkeypatch):
    _set_api_keys(monkeypatch)
    monkeypatch.setattr(handler, "handle_post_deployment", lambda event: {"statusCode": 200, "body": "post"})
    monkeypatch.setattr(handler, "handle_patch_deployment", lambda event, deployment_id: {"statusCode": 200, "body": deployment_id})
    monkeypatch.setattr(handler, "handle_delete_deployment", lambda event, deployment_id: {"statusCode": 200, "body": deployment_id})

    headers = {"x-api-key": "deployments-key"}

    create_response = handler.handler(
        _http_event("POST", "/deployments", body={"name": "A", "description": "B"}, headers=headers),
        None,
    )
    update_response = handler.handler(
        _http_event("PATCH", "/deployments/dep-1", body={"name": "updated"}, headers=headers),
        None,
    )
    delete_response = handler.handler(
        _http_event("DELETE", "/deployments/dep-1", headers=headers),
        None,
    )

    assert create_response["statusCode"] == 200
    assert update_response["statusCode"] == 200
    assert delete_response["statusCode"] == 200


def test_deployments_key_can_manage_nested_deployment_devices(monkeypatch):
    _set_api_keys(monkeypatch)
    monkeypatch.setattr(handler, "handle_post_deployment_device", lambda event, deployment_id: {"statusCode": 200, "body": deployment_id})
    monkeypatch.setattr(handler, "handle_patch_deployment_device", lambda event, deployment_id, device_id: {"statusCode": 200, "body": f"{deployment_id}/{device_id}"})
    monkeypatch.setattr(handler, "handle_delete_deployment_device", lambda event, deployment_id, device_id: {"statusCode": 200, "body": f"{deployment_id}/{device_id}"})

    headers = {"x-api-key": "deployments-key"}

    create_response = handler.handler(
        _http_event("POST", "/deployments/dep-1/devices", body={"device_id": "device-1"}, headers=headers),
        None,
    )
    update_response = handler.handler(
        _http_event("PATCH", "/deployments/dep-1/devices/device-1", body={"name": "North plot"}, headers=headers),
        None,
    )
    delete_response = handler.handler(
        _http_event("DELETE", "/deployments/dep-1/devices/device-1", headers=headers),
        None,
    )

    assert create_response["statusCode"] == 200
    assert update_response["statusCode"] == 200
    assert delete_response["statusCode"] == 200


def test_handle_get_classifications_forwards_dashboard_filters(monkeypatch):
    captured = {}

    monkeypatch.setattr(handler.dynamodb, "list_device_ids_for_deployment", lambda deployment_id: ["device-1", "device-2"])

    def fake_list_classifications(**kwargs):
        captured["kwargs"] = kwargs
        return {"items": [], "count": 0}

    monkeypatch.setattr(handler.dynamodb, "list_classifications", fake_list_classifications)

    response = handler.handle_get_classifications(
        _http_event(
            "GET",
            "/classifications",
            query={
                "deployment_id": "dep-1",
                "taxonomy_level": "species",
                "min_confidence": "0.8",
                "limit": "25",
                "sort_by": "timestamp",
                "sort_desc": "true",
            },
            raw_query="device_id=device-1&device_id=device-2&selected_taxa=Apis%20mellifera&selected_taxa=Bombus%20impatiens",
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1", "device-2"],
        "model_id": None,
        "start_time": None,
        "end_time": None,
        "min_confidence": 0.8,
        "taxonomy_level": "species",
        "selected_taxa": ["Apis mellifera", "Bombus impatiens"],
        "limit": 25,
        "next_token": None,
        "sort_by": "timestamp",
        "sort_desc": True,
    }


def test_handle_count_classifications_uses_scoped_count_helper(monkeypatch):
    captured = {}

    def fake_count_classifications(**kwargs):
        captured["kwargs"] = kwargs
        return {"count": 7}

    monkeypatch.setattr(handler.dynamodb, "count_classifications", fake_count_classifications)

    response = handler.handle_count_classifications(
        _http_event(
            "GET",
            "/classifications/count",
            query={
                "device_id": "device-1",
                "start_time": "2026-03-01T00:00:00Z",
                "end_time": "2026-03-31T23:59:59Z",
                "taxonomy_level": "genus",
                "min_confidence": "0.7",
            },
            raw_query="selected_taxa=Bombus",
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1"],
        "model_id": None,
        "start_time": "2026-03-01T00:00:00Z",
        "end_time": "2026-03-31T23:59:59Z",
        "min_confidence": 0.7,
        "taxonomy_level": "genus",
        "selected_taxa": ["Bombus"],
    }


def test_handle_get_classifications_taxa_count_forwards_filters(monkeypatch):
    captured = {}

    def fake_taxa_count(**kwargs):
        captured["kwargs"] = kwargs
        return {"counts": [{"taxa": "Bombus", "count": 3}]}

    monkeypatch.setattr(handler.dynamodb, "get_classification_taxa_count", fake_taxa_count)

    response = handler.handle_get_classifications_taxa_count(
        _http_event(
            "GET",
            "/classifications/taxa_count",
            query={
                "device_id": "device-1",
                "taxonomy_level": "genus",
                "sort_desc": "true",
            },
            raw_query="selected_taxa=Bombus",
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1"],
        "model_id": None,
        "start_time": None,
        "end_time": None,
        "min_confidence": None,
        "taxonomy_level": "genus",
        "selected_taxa": ["Bombus"],
        "sort_desc": True,
    }


def test_handle_get_environment_time_series_forwards_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(handler.dynamodb, "list_device_ids_for_deployment", lambda deployment_id: ["device-1", "device-2"])

    def fake_environment_time_series(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "temperature": [20.0],
            "humidity": [60.0],
            "pm1p0": [1.0],
            "pm2p5": [2.0],
            "pm4p0": [3.0],
            "pm10": [4.0],
            "voc": [5.0],
            "nox": [6.0],
            "start_time": "2026-03-25T00:00:00",
            "interval_length": 1,
            "interval_unit": "h",
        }

    monkeypatch.setattr(handler.dynamodb, "get_environment_time_series", fake_environment_time_series)

    response = handler.handle_get_environment_time_series(
        _http_event(
            "GET",
            "/environment/time_series",
            query={
                "deployment_id": "dep-1",
                "start_time": "2026-03-25T00:00:00Z",
                "end_time": "2026-03-25T12:00:00Z",
                "interval_length": "1",
                "interval_unit": "h",
            },
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1", "device-2"],
        "start_time": "2026-03-25T00:00:00Z",
        "end_time": "2026-03-25T12:00:00Z",
        "interval_length": 1,
        "interval_unit": "h",
    }
