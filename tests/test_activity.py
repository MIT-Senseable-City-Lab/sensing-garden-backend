import json
from datetime import datetime, timezone

import activity
import handler
from routes import admin


class FakeActivityTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)

    def query(self, **kwargs):
        if self.items:
            items = self.items
            self.items = []
            return {"Items": items}
        return {"Items": []}


def _http_event(method, path, query=None, headers=None):
    event = {"requestContext": {"http": {"method": method, "path": path}}}
    if query is not None:
        event["queryStringParameters"] = query
    if headers is not None:
        event["headers"] = headers
    return event


def test_activity_event_item_has_ttl_and_keys():
    event = activity.ActivityEvent(
        timestamp=datetime(2026, 4, 12, tzinfo=timezone.utc),
        source=activity.ActivitySource.BACKEND,
        event_type=activity.ActivityEventType.DEVICE_SETUP,
        message="Device setup request -> 200",
    )

    item = activity.activity_item(event)

    assert item["event_date"] == "2026-04-12"
    assert item["timestamp_event_id"].startswith("2026-04-12T00:00:00+00:00#")
    assert item["ttl"] > 0


def test_admin_activity_route_returns_events(monkeypatch):
    fake_table = FakeActivityTable()
    fake_table.items.append(
        activity.activity_item(
            activity.ActivityEvent(
                timestamp=datetime.now(timezone.utc),
                source=activity.ActivitySource.BACKEND,
                event_type=activity.ActivityEventType.UPLOAD_URL_REQUESTED,
                device_id="device-1",
                message="Upload URL requested -> 200",
            )
        )
    )
    monkeypatch.setattr(activity.dynamodb, "Table", lambda name: fake_table)

    response = admin.handle_activity(_http_event("GET", "/admin/activity", query={"device_id": "device-1"}))
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["count"] == 1
    assert body["items"][0]["device_id"] == "device-1"


def test_readonly_key_can_read_activity(monkeypatch):
    monkeypatch.setenv("FRONTEND_API_KEY", "frontend-key")
    routes = dict(handler.ROUTES)
    routes[("GET", "/admin/activity")] = lambda event: {"statusCode": 200, "body": "ok"}
    monkeypatch.setattr(handler, "ROUTES", routes)

    response = handler.handler(
        _http_event("GET", "/admin/activity", headers={"x-api-key": "frontend-key"}),
        None,
    )

    assert response["statusCode"] == 200
