import json

from auth import validate_api_key
import handler


def _replace_route(monkeypatch, method, path, route_handler):
    routes = dict(handler.ROUTES)
    routes[(method, path)] = route_handler
    monkeypatch.setattr(handler, "ROUTES", routes)


def _replace_parameterized_route(monkeypatch, method, route_pattern, route_handler):
    parameterized_routes = []
    for route_method, pattern, existing_handler in handler.PARAMETERIZED_ROUTES:
        if route_method == method and pattern.pattern == route_pattern:
            parameterized_routes.append((route_method, pattern, route_handler))
        else:
            parameterized_routes.append((route_method, pattern, existing_handler))
    monkeypatch.setattr(handler, "PARAMETERIZED_ROUTES", tuple(parameterized_routes))


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

    ok, message = validate_api_key({"headers": {"X-Api-Key": "admin-key"}})

    assert ok is True
    assert message == ""


def test_get_routes_require_api_key(monkeypatch):
    _set_api_keys(monkeypatch)

    response = handler.handler(_http_event("GET", "/devices"), None)

    assert response["statusCode"] == 401


def test_deployments_key_can_read_allowed_route(monkeypatch):
    _set_api_keys(monkeypatch)
    _replace_route(monkeypatch, "GET", "/classifications", lambda event: {"statusCode": 200, "body": "ok"})

    response = handler.handler(
        _http_event("GET", "/classifications", headers={"x-api-key": "deployments-key"}),
        None,
    )

    assert response["statusCode"] == 200


def test_frontend_key_can_read_tracks_and_heartbeats(monkeypatch):
    _set_api_keys(monkeypatch)
    _replace_route(monkeypatch, "GET", "/tracks", lambda event: {"statusCode": 200, "body": "tracks"})
    _replace_route(monkeypatch, "GET", "/heartbeats", lambda event: {"statusCode": 200, "body": "heartbeats"})

    tracks_response = handler.handler(
        _http_event("GET", "/tracks", headers={"x-api-key": "frontend-key"}),
        None,
    )
    heartbeats_response = handler.handler(
        _http_event("GET", "/heartbeats", headers={"x-api-key": "frontend-key"}),
        None,
    )

    assert tracks_response["statusCode"] == 200
    assert heartbeats_response["statusCode"] == 200


def test_frontend_key_is_read_only(monkeypatch):
    _set_api_keys(monkeypatch)
    _replace_route(monkeypatch, "GET", "/classifications", lambda event: {"statusCode": 200, "body": "ok"})

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
    _replace_route(monkeypatch, "POST", "/deployments", lambda event: {"statusCode": 200, "body": "post"})
    _replace_parameterized_route(
        monkeypatch,
        "PATCH",
        r"^/deployments/(?P<deployment_id>[^/]+)$",
        lambda event, deployment_id: {"statusCode": 200, "body": deployment_id},
    )
    _replace_parameterized_route(
        monkeypatch,
        "DELETE",
        r"^/deployments/(?P<deployment_id>[^/]+)$",
        lambda event, deployment_id: {"statusCode": 200, "body": deployment_id},
    )

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
    _replace_parameterized_route(
        monkeypatch,
        "POST",
        r"^/deployments/(?P<deployment_id>[^/]+)/devices$",
        lambda event, deployment_id: {"statusCode": 200, "body": deployment_id},
    )
    _replace_parameterized_route(
        monkeypatch,
        "PATCH",
        r"^/deployments/(?P<deployment_id>[^/]+)/devices/(?P<device_id>[^/]+)$",
        lambda event, deployment_id, device_id: {"statusCode": 200, "body": f"{deployment_id}/{device_id}"},
    )
    _replace_parameterized_route(
        monkeypatch,
        "DELETE",
        r"^/deployments/(?P<deployment_id>[^/]+)/devices/(?P<device_id>[^/]+)$",
        lambda event, deployment_id, device_id: {"statusCode": 200, "body": f"{deployment_id}/{device_id}"},
    )

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

    response = handler.classifications.handle_get(
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

    response = handler.classifications.handle_get_count(
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

    def fake_get_classification_taxa_count(**kwargs):
        captured["kwargs"] = kwargs
        return {"counts": [{"taxa": "Bombus", "count": 1}]}

    monkeypatch.setattr(handler.dynamodb, "get_classification_taxa_count", fake_get_classification_taxa_count)

    response = handler.classifications.handle_get_taxa_count(
        _http_event(
            "GET",
            "/classifications/taxa_count",
            query={
                "device_id": "device-1",
                "taxonomy_level": "genus",
                "min_confidence": "0.5",
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
        "min_confidence": 0.5,
        "taxonomy_level": "genus",
        "selected_taxa": ["Bombus"],
        "sort_desc": True,
    }


def test_handle_get_classifications_time_series_forwards_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(handler.dynamodb, "list_device_ids_for_deployment", lambda deployment_id: ["device-1", "device-2"])

    def fake_get_classification_time_series(**kwargs):
        captured["kwargs"] = kwargs
        return {"counts": [1, 2]}

    monkeypatch.setattr(handler.dynamodb, "get_classification_time_series", fake_get_classification_time_series)

    response = handler.classifications.handle_get_time_series(
        _http_event(
            "GET",
            "/classifications/time_series",
            query={
                "deployment_id": "dep-1",
                "model_id": "model-1",
                "start_time": "2026-03-01T00:00:00Z",
                "end_time": "2026-03-31T23:59:59Z",
                "min_confidence": "0.8",
                "taxonomy_level": "species",
                "interval_length": "1",
                "interval_unit": "d",
            },
            raw_query="selected_taxa=Apis%20mellifera",
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1", "device-2"],
        "model_id": "model-1",
        "start_time": "2026-03-01T00:00:00Z",
        "end_time": "2026-03-31T23:59:59Z",
        "min_confidence": 0.8,
        "taxonomy_level": "species",
        "selected_taxa": ["Apis mellifera"],
        "interval_length": 1,
        "interval_unit": "d",
    }


def test_handle_get_environment_time_series_forwards_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(handler.dynamodb, "list_device_ids_for_deployment", lambda deployment_id: ["device-1", "device-2"])

    def fake_get_environment_time_series(**kwargs):
        captured["kwargs"] = kwargs
        return {"temperature": [20.0]}

    monkeypatch.setattr(handler.dynamodb, "get_environment_time_series", fake_get_environment_time_series)

    response = handler.environment.handle_get_time_series(
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


def test_handle_get_tracks_forwards_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(handler.dynamodb, "list_device_ids_for_deployment", lambda deployment_id: ["device-1", "device-2"])

    def fake_list_tracks(**kwargs):
        captured["kwargs"] = kwargs
        return {"items": [], "count": 0}

    monkeypatch.setattr(handler.dynamodb, "list_tracks", fake_list_tracks)

    response = handler.tracks.handle_get(
        _http_event(
            "GET",
            "/tracks",
            query={
                "deployment_id": "dep-1",
                "start_time": "2026-03-01T00:00:00Z",
                "end_time": "2026-03-31T23:59:59Z",
                "limit": "10",
                "sort_by": "timestamp",
                "sort_desc": "true",
            },
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1", "device-2"],
        "start_time": "2026-03-01T00:00:00Z",
        "end_time": "2026-03-31T23:59:59Z",
        "limit": 10,
        "next_token": None,
        "sort_by": "timestamp",
        "sort_desc": True,
    }


def test_handle_get_tracks_count_forwards_filters(monkeypatch):
    captured = {}

    def fake_count_tracks(**kwargs):
        captured["kwargs"] = kwargs
        return {"count": 3}

    monkeypatch.setattr(handler.dynamodb, "count_tracks", fake_count_tracks)

    response = handler.tracks.handle_get_count(
        _http_event(
            "GET",
            "/tracks/count",
            query={
                "device_id": "device-1",
                "start_time": "2026-03-01T00:00:00Z",
                "end_time": "2026-03-31T23:59:59Z",
            },
        )
    )

    assert response["statusCode"] == 200
    assert captured["kwargs"] == {
        "device_ids": ["device-1"],
        "start_time": "2026-03-01T00:00:00Z",
        "end_time": "2026-03-31T23:59:59Z",
    }


def test_handle_get_track_adds_composite_url(monkeypatch):
    monkeypatch.setattr(
        handler.dynamodb,
        "get_track",
        lambda track_id: {
            "track_id": track_id,
            "timestamp": "2026-03-10T12:00:00+00:00",
            "composite_key": "outputs/track-1.jpg",
        },
    )
    monkeypatch.setattr(handler.tracks, "generate_presigned_url", lambda key, bucket: f"{bucket}/{key}")

    response = handler.tracks.handle_get_single(_http_event("GET", "/tracks/track-1"), "track-1")

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["track"]["composite_url"] == "scl-sensing-garden/outputs/track-1.jpg"
    assert payload["track"]["timestamp"] == "2026-03-10T12:00:00"


def test_parameterized_track_route_dispatches(monkeypatch):
    _set_api_keys(monkeypatch)
    _replace_parameterized_route(
        monkeypatch,
        "GET",
        r"^/tracks/(?P<track_id>[^/]+)$",
        lambda event, track_id: {"statusCode": 200, "body": track_id},
    )

    response = handler.handler(
        _http_event("GET", "/tracks/track-123", headers={"x-api-key": "admin-key"}),
        None,
    )

    assert response["statusCode"] == 200


def test_frontend_key_can_read_parameterized_track_route(monkeypatch):
    _set_api_keys(monkeypatch)
    _replace_parameterized_route(
        monkeypatch,
        "GET",
        r"^/tracks/(?P<track_id>[^/]+)$",
        lambda event, track_id: {"statusCode": 200, "body": track_id},
    )

    response = handler.handler(
        _http_event("GET", "/tracks/track-123", headers={"x-api-key": "frontend-key"}),
        None,
    )

    assert response["statusCode"] == 200


def test_handle_get_heartbeats_reads_latest_items(monkeypatch):
    monkeypatch.setattr(handler.dynamodb, "get_latest_heartbeats", lambda: {"items": [{"timestamp": "2026-03-10T12:00:00+00:00"}], "count": 1})

    response = handler.heartbeats.handle_get(_http_event("GET", "/heartbeats"))

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["count"] == 1
    assert payload["items"][0]["timestamp"] == "2026-03-10T12:00:00"


def test_deleted_routes_return_404(monkeypatch):
    _set_api_keys(monkeypatch)
    headers = {"x-api-key": "admin-key"}

    for method, path in (
        ("POST", "/devices"),
        ("POST", "/detections"),
        ("POST", "/classifications"),
        ("POST", "/videos"),
        ("POST", "/videos/register"),
        ("POST", "/environment"),
        ("GET", "/detections/csv"),
        ("GET", "/classifications/csv"),
        ("GET", "/models/csv"),
        ("GET", "/videos/csv"),
        ("GET", "/environment/csv"),
        ("GET", "/devices/csv"),
    ):
        response = handler.handler(_http_event(method, path, headers=headers), None)
        assert response["statusCode"] == 404
