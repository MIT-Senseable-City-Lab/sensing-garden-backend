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


class ActivityLevel(str, Enum):
    INFO = "INFO"
    ERROR = "ERROR"


class ActivityEventType(str, Enum):
    S3_OBJECT_RECEIVED = "s3_object_received"
    S3_OBJECT_PROCESSED = "s3_object_processed"
    OBJECT_IGNORED = "object_ignored"
    RESULTS_MALFORMED = "results_malformed"
    TRACK_VALIDATION_FAILED = "track_validation_failed"
    CLASSIFICATION_VALIDATION_FAILED = "classification_validation_failed"
    COMPOSITE_GENERATION_FAILED = "composite_generation_failed"


class TriggerFailureReason(str, Enum):
    MALFORMED_JSON = "malformed_json"
    VALIDATION_FAILED = "validation_failed"
    GENERATION_FAILED = "generation_failed"
    OUTSIDE_V1_PREFIX = "outside_v1_prefix"
    UNSUPPORTED_KEY = "unsupported_key"


class ActivityEvent(BaseModel):
    timestamp: datetime
    source: ActivitySource
    event_type: ActivityEventType
    message: str
    actor_type: str = "s3_trigger"
    device_id: str | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    track_id: str | None = None
    level: ActivityLevel | None = None
    reason: TriggerFailureReason | None = None
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


def _string_metadata(**fields: object) -> dict[str, str]:
    return {name: str(value) for name, value in fields.items() if value is not None}


def _record_trigger_event(
    event_type: ActivityEventType,
    bucket: str,
    key: str,
    message: str,
    *,
    level: ActivityLevel,
    track_id: str | None = None,
    reason: TriggerFailureReason | None = None,
    **metadata: object,
) -> None:
    record_activity_event(
        ActivityEvent(
            timestamp=utc_now(),
            source=ActivitySource.S3_TRIGGER,
            event_type=event_type,
            device_id=device_id_from_key(key),
            s3_bucket=bucket,
            s3_key=key,
            track_id=track_id,
            level=level,
            reason=reason,
            message=message,
            metadata=_string_metadata(**metadata),
        )
    )


def record_s3_received(bucket: str, key: str, kind: str) -> None:
    _record_trigger_event(
        ActivityEventType.S3_OBJECT_RECEIVED,
        bucket,
        key,
        "S3 object received",
        level=ActivityLevel.INFO,
        kind=kind,
    )


def record_s3_processed(bucket: str, key: str, kind: str, status: str, counts: dict[str, int]) -> None:
    _record_trigger_event(
        ActivityEventType.S3_OBJECT_PROCESSED,
        bucket,
        key,
        f"S3 object processed: {status}",
        level=ActivityLevel.ERROR if status == "error" else ActivityLevel.INFO,
        kind=kind,
        status=status,
        **counts,
    )


def record_object_ignored(bucket: str, key: str, reason: TriggerFailureReason) -> None:
    _record_trigger_event(
        ActivityEventType.OBJECT_IGNORED,
        bucket,
        key,
        f"S3 object ignored: {reason.value}",
        level=ActivityLevel.INFO,
        reason=reason,
    )


def record_results_malformed(bucket: str, key: str, error: str) -> None:
    _record_trigger_event(
        ActivityEventType.RESULTS_MALFORMED,
        bucket,
        key,
        "Results JSON malformed",
        level=ActivityLevel.ERROR,
        reason=TriggerFailureReason.MALFORMED_JSON,
        error=error,
    )


def record_track_validation_failed(bucket: str, key: str, track_id: str | None, error: str) -> None:
    _record_trigger_event(
        ActivityEventType.TRACK_VALIDATION_FAILED,
        bucket,
        key,
        "Track validation failed",
        level=ActivityLevel.ERROR,
        track_id=track_id,
        reason=TriggerFailureReason.VALIDATION_FAILED,
        error=error,
    )


def record_classification_validation_failed(
    bucket: str,
    key: str,
    track_id: str | None,
    frame_number: object,
    error: str,
) -> None:
    _record_trigger_event(
        ActivityEventType.CLASSIFICATION_VALIDATION_FAILED,
        bucket,
        key,
        "Classification validation failed",
        level=ActivityLevel.ERROR,
        track_id=track_id,
        reason=TriggerFailureReason.VALIDATION_FAILED,
        frame_number=frame_number,
        error=error,
    )


def record_composite_generation_failed(bucket: str, key: str, track_id: str | None, error: str) -> None:
    _record_trigger_event(
        ActivityEventType.COMPOSITE_GENERATION_FAILED,
        bucket,
        key,
        "Composite generation failed",
        level=ActivityLevel.ERROR,
        track_id=track_id,
        reason=TriggerFailureReason.GENERATION_FAILED,
        error=error,
    )
