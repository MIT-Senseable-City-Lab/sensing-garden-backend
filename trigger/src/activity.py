from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import boto3
from pydantic import BaseModel, Field


ACTIVITY_EVENTS_TABLE = os.environ.get("ACTIVITY_EVENTS_TABLE", "sensing-garden-activity-events")
ACTIVITY_RETENTION_DAYS = int(os.environ.get("ACTIVITY_RETENTION_DAYS", "30"))
dynamodb = boto3.resource("dynamodb")


class ActivitySource(str, Enum):
    S3_TRIGGER = "s3_trigger"


class ActivityEventType(str, Enum):
    S3_OBJECT_PROCESSED = "s3_object_processed"


class ActivityEvent(BaseModel):
    timestamp: datetime
    source: ActivitySource
    event_type: ActivityEventType
    message: str
    actor_type: str = "s3_trigger"
    device_id: str | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    level: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def device_id_from_key(key: str) -> str | None:
    parts = key.split("/", 3)
    if len(parts) >= 3 and parts[0] == "v1":
        return parts[1]
    return None


def activity_item(event: ActivityEvent) -> dict[str, Any]:
    timestamp = event.timestamp.astimezone(timezone.utc)
    item = event.model_dump(mode="json", exclude_none=True)
    item["event_date"] = timestamp.date().isoformat()
    item["timestamp_event_id"] = f"{timestamp.isoformat()}#{uuid.uuid4().hex}"
    item["ttl"] = int((timestamp + timedelta(days=ACTIVITY_RETENTION_DAYS)).timestamp())
    return item


def record_activity_event(event: ActivityEvent) -> None:
    dynamodb.Table(ACTIVITY_EVENTS_TABLE).put_item(Item=activity_item(event))


def record_s3_processed(bucket: str, key: str, status: str, counts: dict[str, int]) -> None:
    record_activity_event(
        ActivityEvent(
            timestamp=utc_now(),
            source=ActivitySource.S3_TRIGGER,
            event_type=ActivityEventType.S3_OBJECT_PROCESSED,
            device_id=device_id_from_key(key),
            s3_bucket=bucket,
            s3_key=key,
            level="ERROR" if status == "error" else "INFO",
            message=f"S3 object processed: {status}",
            metadata={name: str(value) for name, value in counts.items()},
        )
    )
