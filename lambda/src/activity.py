from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, Field


ACTIVITY_EVENTS_TABLE = os.environ.get("ACTIVITY_EVENTS_TABLE", "sensing-garden-activity-events")
ACTIVITY_RETENTION_DAYS = int(os.environ.get("ACTIVITY_RETENTION_DAYS", "30"))
dynamodb = boto3.resource("dynamodb")


class ActivitySource(str, Enum):
    BACKEND = "backend"
    S3_TRIGGER = "s3_trigger"


class ActivityEventType(str, Enum):
    API_REQUEST = "api_request"
    DEVICE_SETUP = "device_setup"
    UPLOAD_URL_REQUESTED = "upload_url_requested"
    S3_OBJECT_PROCESSED = "s3_object_processed"


class ActivityEvent(BaseModel):
    timestamp: datetime
    source: ActivitySource
    event_type: ActivityEventType
    message: str
    actor_type: str = "backend"
    device_id: str | None = None
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    level: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def activity_item(event: ActivityEvent) -> dict[str, Any]:
    timestamp = event.timestamp.astimezone(timezone.utc)
    item = event.model_dump(mode="json", exclude_none=True)
    item["event_date"] = timestamp.date().isoformat()
    item["timestamp_event_id"] = f"{timestamp.isoformat()}#{uuid.uuid4().hex}"
    item["ttl"] = int((timestamp + timedelta(days=ACTIVITY_RETENTION_DAYS)).timestamp())
    return item


def record_activity_event(event: ActivityEvent) -> None:
    dynamodb.Table(ACTIVITY_EVENTS_TABLE).put_item(Item=activity_item(event))


def _query_day(day: datetime, limit: int) -> list[dict[str, Any]]:
    response = dynamodb.Table(ACTIVITY_EVENTS_TABLE).query(
        KeyConditionExpression=Key("event_date").eq(day.date().isoformat()),
        ScanIndexForward=False,
        Limit=limit,
    )
    return list(response.get("Items", []))


def _matches(item: dict[str, Any], source: str, device_id: str, query: str) -> bool:
    text = f"{item.get('message', '')} {item.get('s3_key', '')} {item.get('path', '')}".lower()
    return (
        (not source or item.get("source") == source)
        and (not device_id or item.get("device_id") == device_id)
        and (not query or query.lower() in text)
    )


def list_activity_events(source: str, device_id: str, query: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    today = utc_now()
    for offset in range(ACTIVITY_RETENTION_DAYS):
        for item in _query_day(today - timedelta(days=offset), limit):
            if _matches(item, source, device_id, query):
                rows.append(item)
            if len(rows) >= limit:
                return rows
    return rows
