import json
import logging
import os
import re
import hashlib
import posixpath
import tarfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

import activity
from composites import (
    CompositeSkipReason,
    CompositeStatus,
    candidate_composite_keys,
    ensure_track_composite,
    iter_result_tracks,
)
from schemas import Classification, Device, EnvironmentalReading, Heartbeat, Track, Video


TRACKS_TABLE = os.environ.get("TRACKS_TABLE", "sensing-garden-tracks")
CLASSIFICATIONS_TABLE = os.environ.get("CLASSIFICATIONS_TABLE", "sensing-garden-classifications")
DEVICES_TABLE = os.environ.get("DEVICES_TABLE", "sensing-garden-devices")
VIDEOS_TABLE = os.environ.get("VIDEOS_TABLE", "sensing-garden-videos")
HEARTBEATS_TABLE = os.environ.get("HEARTBEATS_TABLE", "sensing-garden-heartbeats")
ENVIRONMENTAL_TABLE = os.environ.get("ENVIRONMENTAL_TABLE", "sensing-garden-environmental-readings")
PROCESSED_OBJECTS_TABLE = os.environ.get("PROCESSED_OBJECTS_TABLE", "")
PROCESSED_OBJECT_RETENTION_DAYS = int(os.environ.get("PROCESSED_OBJECT_RETENTION_DAYS", "30"))
PROCESSED_OBJECT_LEASE_SECONDS = 360
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
MODEL_ID = os.environ.get("MODEL_ID", "")
DEPLOYMENT_ID = os.environ.get("DEPLOYMENT_ID")
HEARTBEAT_KEY_PATTERN = re.compile(r"^v1/[^/]+/heartbeats/[^/]+\.json$")
ENVIRONMENT_KEY_PATTERN = re.compile(r"^v1/[^/]+/environment/[^/]+\.json$")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class S3TriggerAction(str, Enum):
    RECEIVED = "received"
    IGNORED = "ignored"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    IDEMPOTENCY_UNAVAILABLE = "idempotency_unavailable"
    IDEMPOTENCY_ERROR = "idempotency_error"


class ProcessingKind(str, Enum):
    ARCHIVE = "archive"
    RESULTS = "results"
    HEARTBEAT = "heartbeat"
    ENVIRONMENT = "environment"
    VIDEO = "video"
    IGNORED = "ignored"


# Hourly batch archives live in the v2 namespace; their members are canonical
# v1/ keys. In this (index) approach the media stays inside the tar and each
# record is stamped with the tar's location plus the member's byte range, so a
# range-reading serve path can fetch the bytes without re-exploding to S3.
ARCHIVE_SUFFIXES = (".tar",)
ARCHIVE_KEY_PREFIX = "v2/archives/"

# Video members are indexed on their own (not only via a co-located results.json),
# so a video that lands in an archive without its results -- a sampled video with no
# detections, a DOT video, or a capture split across archives -- is still mapped.
VIDEO_MEMBER_SUFFIX = ".mp4"

# Device-local sidecars that are never bundled / processed.
ARCHIVE_SKIP_NAMES = frozenset(
    {".done", ".detection.json", ".expected_tracks", ".completed_tracks", ".uploaded", ".archived", ".archived-aux"}
)


def _is_safe_archive_member(name: str) -> bool:
    """Reject anything that is not a canonical v1/ key or that path-traverses."""
    if not name or name.startswith("/"):
        return False
    if not name.startswith("v1/"):
        return False
    if posixpath.normpath(name) != name or ".." in name.split("/"):
        return False
    if Path(name).name in ARCHIVE_SKIP_NAMES:
        return False
    return True


class ProcessedObjectStatus(str, Enum):
    PROCESSING = "processing"
    PROCESSED = "processed"


class IdempotencyDecision(str, Enum):
    PROCESS = "process"
    SKIP_DUPLICATE = "skip_duplicate"
    IN_FLIGHT = "in_flight"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class S3ObjectEvent:
    bucket: str
    key: str
    etag: Optional[str]
    version_id: Optional[str]

    @property
    def object_version(self) -> Optional[str]:
        return self.version_id or self.etag

    @property
    def object_id(self) -> Optional[str]:
        if self.object_version is None:
            return None
        identity = json.dumps([self.bucket, self.key, self.object_version], separators=(",", ":"))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdempotencyClaim:
    decision: IdempotencyDecision
    attempt_id: Optional[str] = None


def log_s3_trigger(action: S3TriggerAction, bucket: str, key: str, **fields: Any) -> None:
    logger.info(
        json.dumps(
            {
                "component": "s3_trigger",
                "action": action.value,
                "bucket": bucket,
                "key": key,
                **fields,
            },
            sort_keys=True,
            default=str,
        )
    )


class StorageAdapter:
    def read_text(
        self,
        bucket: str,
        key: str,
        *,
        version_id: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    def read_json(
        self,
        bucket: str,
        key: str,
        *,
        version_id: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> Dict[str, Any]:
        return json.loads(self.read_text(bucket, key, version_id=version_id, etag=etag))

    def read_bytes(self, bucket: str, key: str) -> bytes:
        raise NotImplementedError

    def write_bytes(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        raise NotImplementedError

    def exists(self, bucket: str, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> List[str]:
        raise NotImplementedError


class S3StorageAdapter(StorageAdapter):
    def __init__(self) -> None:
        self.client = boto3.client("s3")

    def read_text(
        self,
        bucket: str,
        key: str,
        *,
        version_id: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> str:
        request: Dict[str, Any] = {"Bucket": bucket, "Key": key}
        if version_id is not None:
            request["VersionId"] = version_id
        if etag is not None:
            request["IfMatch"] = etag if etag.startswith('"') else f'"{etag}"'
        response = self.client.get_object(**request)
        return response["Body"].read().decode("utf-8")

    def read_bytes(self, bucket: str, key: str) -> bytes:
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def write_bytes(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> List[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: List[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not suffix or key.endswith(suffix):
                    keys.append(key)
        return keys


class LocalStorageAdapter(StorageAdapter):
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def read_text(
        self,
        bucket: str,
        key: str,
        *,
        version_id: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> str:
        return self._path(key).read_text()

    def read_bytes(self, bucket: str, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(key).exists()

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> List[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        keys: List[str] = []
        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(self.root).as_posix()
                if not suffix or rel.endswith(suffix):
                    keys.append(rel)
        return sorted(keys)


class TarStorageAdapter(StorageAdapter):
    """Reads from an in-memory (uncompressed) tar; falls back to S3 for non-members.

    The archive is uncompressed, so each member's ``offset_data`` and ``size`` are
    byte offsets into the raw archive bytes -- exposed via :meth:`member_range` so
    records can carry a range a serve path can fetch with a single ranged GET.
    Reads for keys not in the tar (notably ``v1/manifest.json``) defer to S3.
    Generated artifacts (composites the device did not supply) are written through
    to S3, since they cannot be added to the immutable archive.
    """

    def __init__(self, archive_bytes: bytes, fallback: StorageAdapter) -> None:
        self._archive_bytes = archive_bytes
        self._fallback = fallback
        self._ranges: Dict[str, Tuple[int, int]] = {}
        with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:") as tar:
            for member in tar.getmembers():
                if member.isfile() and _is_safe_archive_member(member.name):
                    self._ranges[member.name] = (member.offset_data, member.size)

    def member_names(self) -> List[str]:
        return list(self._ranges)

    def member_range(self, key: str) -> Optional[Tuple[int, int]]:
        return self._ranges.get(key)

    def _member_bytes(self, key: str) -> bytes:
        offset, size = self._ranges[key]
        return self._archive_bytes[offset:offset + size]

    def read_text(self, bucket, key, *, version_id=None, etag=None) -> str:
        if key in self._ranges:
            return self._member_bytes(key).decode("utf-8")
        return self._fallback.read_text(bucket, key, version_id=version_id, etag=etag)

    def read_bytes(self, bucket: str, key: str) -> bytes:
        if key in self._ranges:
            return self._member_bytes(key)
        return self._fallback.read_bytes(bucket, key)

    def write_bytes(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self._fallback.write_bytes(bucket, key, body, content_type)

    def exists(self, bucket: str, key: str) -> bool:
        return key in self._ranges or self._fallback.exists(bucket, key)

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> List[str]:
        members = [k for k in self._ranges if k.startswith(prefix) and (not suffix or k.endswith(suffix))]
        return sorted(set(members) | set(self._fallback.list_keys(bucket, prefix, suffix)))


class DynamoWriter:
    def __init__(self):
        resource = boto3.resource("dynamodb")
        self.tracks = resource.Table(TRACKS_TABLE)
        self.classifications = resource.Table(CLASSIFICATIONS_TABLE)
        self.devices = resource.Table(DEVICES_TABLE)
        self.videos = resource.Table(VIDEOS_TABLE)
        self.heartbeats = resource.Table(HEARTBEATS_TABLE)
        self.environmental_readings = resource.Table(ENVIRONMENTAL_TABLE)

    def put_tracks(self, items: List[Dict[str, Any]]) -> None:
        with self.tracks.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def put_classifications(self, items: List[Dict[str, Any]]) -> None:
        with self.classifications.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def put_devices_if_missing(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            try:
                self.devices.update_item(
                    Key={"device_id": item["device_id"]},
                    UpdateExpression=(
                        "SET parent_device_id = :parent_device_id, "
                        "created = if_not_exists(created, :created)"
                    ),
                    ConditionExpression="attribute_not_exists(device_id)",
                    ExpressionAttributeValues={
                        ":parent_device_id": item.get("parent_device_id"),
                        ":created": item.get("created") or datetime.utcnow().isoformat(),
                    },
                )
            except ClientError as exc:
                error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
                if error_code != "ConditionalCheckFailedException":
                    raise

    def put_videos(self, items: List[Dict[str, Any]]) -> None:
        with self.videos.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def put_heartbeats(self, items: List[Dict[str, Any]]) -> None:
        with self.heartbeats.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def put_environmental_readings(self, items: List[Dict[str, Any]]) -> None:
        with self.environmental_readings.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)


class ProcessedObjectStore:
    def __init__(self, table_name: str = PROCESSED_OBJECTS_TABLE):
        self.table = boto3.resource("dynamodb").Table(table_name) if table_name else None

    def begin(self, event: S3ObjectEvent, kind: ProcessingKind) -> IdempotencyClaim:
        object_id = event.object_id
        if object_id is None:
            return IdempotencyClaim(IdempotencyDecision.UNAVAILABLE)
        if self.table is None:
            raise RuntimeError("PROCESSED_OBJECTS_TABLE is required")

        now = _epoch_seconds()
        attempt_id = uuid.uuid4().hex
        item = {
            "object_id": object_id,
            "bucket": event.bucket,
            "s3_key": event.key,
            "etag": event.etag,
            "version_id": event.version_id,
            "kind": kind.value,
            "status": ProcessedObjectStatus.PROCESSING.value,
            "attempt_id": attempt_id,
            "lease_until": now + PROCESSED_OBJECT_LEASE_SECONDS,
            "ttl": now + PROCESSED_OBJECT_LEASE_SECONDS,
            "updated_at": now,
        }
        try:
            self.table.put_item(
                Item={key: value for key, value in item.items() if value is not None},
                ConditionExpression=(
                    "attribute_not_exists(object_id) OR "
                    "(#status = :processing AND lease_until < :now)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":processing": ProcessedObjectStatus.PROCESSING.value,
                    ":now": now,
                },
            )
            return IdempotencyClaim(IdempotencyDecision.PROCESS, attempt_id)
        except ClientError as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                item = self.table.get_item(Key={"object_id": object_id}, ConsistentRead=True).get("Item", {})
                if item.get("status") == ProcessedObjectStatus.PROCESSED.value:
                    return IdempotencyClaim(IdempotencyDecision.SKIP_DUPLICATE)
                return IdempotencyClaim(IdempotencyDecision.IN_FLIGHT)
            raise

    def complete(self, event: S3ObjectEvent, claim: IdempotencyClaim) -> None:
        object_id = event.object_id
        if object_id is None or claim.attempt_id is None:
            return
        if self.table is None:
            raise RuntimeError("PROCESSED_OBJECTS_TABLE is required")

        now = _epoch_seconds()
        self.table.update_item(
            Key={"object_id": object_id},
            UpdateExpression=(
                "SET #status = :processed, #ttl = :ttl, updated_at = :now "
                "REMOVE lease_until, attempt_id"
            ),
            ConditionExpression="#status = :processing AND attempt_id = :attempt_id",
            ExpressionAttributeNames={"#status": "status", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":processing": ProcessedObjectStatus.PROCESSING.value,
                ":processed": ProcessedObjectStatus.PROCESSED.value,
                ":attempt_id": claim.attempt_id,
                ":ttl": now + PROCESSED_OBJECT_RETENTION_DAYS * 24 * 60 * 60,
                ":now": now,
            },
        )

    def fail(self, event: S3ObjectEvent, claim: IdempotencyClaim) -> None:
        object_id = event.object_id
        if object_id is None or claim.attempt_id is None:
            return
        if self.table is None:
            raise RuntimeError("PROCESSED_OBJECTS_TABLE is required")
        try:
            self.table.delete_item(
                Key={"object_id": object_id},
                ConditionExpression="#status = :processing AND attempt_id = :attempt_id",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":processing": ProcessedObjectStatus.PROCESSING.value,
                    ":attempt_id": claim.attempt_id,
                },
            )
        except ClientError as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code != "ConditionalCheckFailedException":
                raise


class CollectingWriter:
    def __init__(self):
        self.tracks: List[Dict[str, Any]] = []
        self.classifications: List[Dict[str, Any]] = []
        self.devices: List[Dict[str, Any]] = []
        self.videos: List[Dict[str, Any]] = []
        self.heartbeats: List[Dict[str, Any]] = []
        self.environmental_readings: List[Dict[str, Any]] = []

    def put_tracks(self, items: List[Dict[str, Any]]) -> None:
        self.tracks.extend(items)

    def put_classifications(self, items: List[Dict[str, Any]]) -> None:
        self.classifications.extend(items)

    def put_devices_if_missing(self, items: List[Dict[str, Any]]) -> None:
        known = {item["device_id"] for item in self.devices}
        for item in items:
            if item["device_id"] not in known:
                device_record = dict(item)
                device_record.setdefault("created", datetime.utcnow().isoformat())
                self.devices.append(device_record)
                known.add(item["device_id"])

    def put_videos(self, items: List[Dict[str, Any]]) -> None:
        self.videos.extend(items)

    def put_heartbeats(self, items: List[Dict[str, Any]]) -> None:
        self.heartbeats.extend(items)

    def put_environmental_readings(self, items: List[Dict[str, Any]]) -> None:
        self.environmental_readings.extend(items)


class ArchiveIndexWriter:
    """Wraps a writer and stamps each record with the archive + byte range of its
    media, so serving can range-read the tar instead of fetching a standalone key.

    A record whose media is not a tar member (e.g. a composite generated server
    side and written to S3) is left unstamped and serves from its flat key.
    """

    def __init__(self, inner: "WriterProtocol", adapter: TarStorageAdapter, bucket: str, archive_key: str) -> None:
        self._inner = inner
        self._adapter = adapter
        self._bucket = bucket
        self._archive_key = archive_key
        # video_keys already emitted (via a results.json), so the standalone-video
        # pass can skip them and avoid writing a duplicate/less-complete row.
        self.seen_video_keys: set = set()

    def _stamp(self, item: Dict[str, Any], key_field: str, prefix: str) -> None:
        member_range = self._adapter.member_range(item.get(key_field))
        if member_range is None:
            return
        offset, size = member_range
        item["archive_bucket"] = self._bucket
        item["archive_key"] = self._archive_key
        item[f"{prefix}_offset"] = offset
        item[f"{prefix}_size"] = size

    def put_tracks(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            self._stamp(item, "composite_key", "composite")
        self._inner.put_tracks(items)

    def put_classifications(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            self._stamp(item, "image_key", "image")
        self._inner.put_classifications(items)

    def put_videos(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            self._stamp(item, "video_key", "video")
            video_key = item.get("video_key")
            if video_key is not None:
                self.seen_video_keys.add(video_key)
        self._inner.put_videos(items)

    def put_devices_if_missing(self, items: List[Dict[str, Any]]) -> None:
        self._inner.put_devices_if_missing(items)

    def put_heartbeats(self, items: List[Dict[str, Any]]) -> None:
        self._inner.put_heartbeats(items)

    def put_environmental_readings(self, items: List[Dict[str, Any]]) -> None:
        self._inner.put_environmental_readings(items)


class WriterProtocol(Protocol):
    def put_tracks(self, items: List[Dict[str, Any]]) -> None:
        ...

    def put_classifications(self, items: List[Dict[str, Any]]) -> None:
        ...

    def put_devices_if_missing(self, items: List[Dict[str, Any]]) -> None:
        ...

    def put_videos(self, items: List[Dict[str, Any]]) -> None:
        ...

    def put_heartbeats(self, items: List[Dict[str, Any]]) -> None:
        ...

    def put_environmental_readings(self, items: List[Dict[str, Any]]) -> None:
        ...


def _convert_floats_to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _convert_floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_floats_to_decimal(v) for v in obj]
    return obj


def _model_dump(model: Any) -> Dict[str, Any]:
    raw = model.model_dump() if hasattr(model, "model_dump") else dict(model.__dict__)
    return _convert_floats_to_decimal(raw)


def _epoch_seconds() -> int:
    return int(datetime.utcnow().timestamp())


def derive_s3_prefix(results_json_key: str) -> str:
    return results_json_key.rsplit("/results.json", 1)[0]


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _derive_base_datetime(results: Dict[str, Any], track: Dict[str, Any], s3_key: str) -> datetime:
    if results.get("video_timestamp"):
        return _parse_datetime(results["video_timestamp"]).replace(microsecond=0, tzinfo=None)
    if results.get("date") and track.get("timestamp"):
        return datetime.strptime(f"{results['date']}{track['timestamp']}", "%Y%m%d%H%M%S")

    prefix_part = derive_s3_prefix(s3_key).rsplit("/", 1)[-1]
    if "_" in prefix_part:
        return datetime.strptime(prefix_part, "%Y%m%d_%H%M%S")
    if track.get("timestamp"):
        return datetime.strptime(f"{prefix_part}{track['timestamp']}", "%Y%m%d%H%M%S")
    raise ValueError(f"Cannot derive timestamp for {s3_key}")


def derive_track_timestamp(results: Dict[str, Any], track: Dict[str, Any], s3_key: str) -> str:
    base = _derive_base_datetime(results, track, s3_key)
    offset_seconds = track.get("first_seen_seconds")
    if offset_seconds is not None:
        base = base + timedelta(seconds=float(offset_seconds))
    return base.isoformat(timespec="microseconds")


def derive_record_track_id(track: Dict[str, Any], s3_key: str) -> str:
    track_id = str(track["track_id"])
    timestamp = track.get("timestamp")
    prefix_part = derive_s3_prefix(s3_key).rsplit("/", 1)[-1]
    if re.fullmatch(r"\d{8}", prefix_part) and timestamp:
        return f"{track_id}_{timestamp}"
    return track_id


def derive_frame_timestamp(results: Dict[str, Any], track: Dict[str, Any], frame: Dict[str, Any], s3_key: str) -> str:
    base = _derive_base_datetime(results, track, s3_key).replace(microsecond=0)
    frame_number = int(frame["frame_number"])
    track_offset_microseconds = int(hashlib.md5(track["track_id"].encode("utf-8")).hexdigest()[:6], 16)
    return (base + timedelta(microseconds=track_offset_microseconds + frame_number)).isoformat(timespec="microseconds")


def _candidate_composite_keys(s3_prefix: str, track: Dict[str, Any]) -> List[str]:
    return candidate_composite_keys(s3_prefix, track)


def _resolve_s3_key(storage: StorageAdapter, bucket: str, candidates: List[str]) -> str:
    for candidate in candidates:
        if storage.exists(bucket, candidate):
            return candidate
    return candidates[0]


def derive_composite_key(storage: StorageAdapter, bucket: str, s3_prefix: str, track: Dict[str, Any]) -> str:
    return _resolve_s3_key(storage, bucket, _candidate_composite_keys(s3_prefix, track))


def _candidate_crop_keys(s3_prefix: str, track: Dict[str, Any], frame_number: int) -> List[str]:
    short_id = track["track_id"][:8]
    frame_part = f"frame_{frame_number:06d}.jpg"
    candidates = [f"{s3_prefix}/crops/{short_id}/{frame_part}"]
    timestamp = track.get("timestamp")
    if timestamp:
        candidates.append(f"{s3_prefix}/crops/{track['track_id']}_{timestamp}/{frame_part}")
        candidates.append(f"{s3_prefix}/crops/{short_id}_{timestamp}/{frame_part}")
    return candidates


def derive_crop_key(storage: StorageAdapter, bucket: str, s3_prefix: str, track: Dict[str, Any], frame: Dict[str, Any]) -> str:
    frame_number = int(frame["frame_number"])
    return _resolve_s3_key(storage, bucket, _candidate_crop_keys(s3_prefix, track, frame_number))


def _load_manifest(storage: StorageAdapter, bucket: str) -> Optional[Dict[str, Any]]:
    manifest_key = "v1/manifest.json"
    if not storage.exists(bucket, manifest_key):
        return None
    return storage.read_json(bucket, manifest_key)


def _resolve_devices(results: Dict[str, Any], manifest: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    created = datetime.utcnow().isoformat()
    if manifest:
        flick_id = manifest.get("flick_id")
        if flick_id:
            devices.append(_model_dump(Device(device_id=flick_id, parent_device_id=None, created=created)))
            for dot_id in manifest.get("dot_ids", []):
                devices.append(_model_dump(Device(device_id=dot_id, parent_device_id=flick_id, created=created)))
        return devices
    return [_model_dump(Device(device_id=results["source_device"], parent_device_id=None, created=created))]


def _resolve_model_id(results: Dict[str, Any]) -> str:
    model_id = results.get("model_id") or MODEL_ID
    if not model_id:
        return "unknown"
    return model_id


def _iter_confirmed_tracks(results: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    return iter_result_tracks(results)


def _load_labels(storage: StorageAdapter, bucket: str, s3_prefix: str, track_id: str, cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    short_id = track_id[:8]
    if short_id not in cache:
        cache[short_id] = storage.read_json(bucket, f"{s3_prefix}/labels/{short_id}.json")
    return cache[short_id]


def get_bbox_from_labels(
    storage: StorageAdapter,
    bucket: str,
    s3_prefix: str,
    track: Dict[str, Any],
    frame_number: int,
    cache: Dict[str, Dict[str, Any]],
) -> Optional[List[float]]:
    try:
        labels = _load_labels(storage, bucket, s3_prefix, track["track_id"], cache)
    except Exception:
        return None
    for frame in labels.get("frames", []):
        if int(frame.get("frame_number", -1)) == frame_number:
            return frame.get("bbox")
    return None


def _build_track_record(
    storage: StorageAdapter,
    bucket: str,
    key: str,
    results: Dict[str, Any],
    track: Dict[str, Any],
) -> Dict[str, Any]:
    prefix = derive_s3_prefix(key)
    track_payload = {
        "track_id": derive_record_track_id(track, key),
        "device_id": results["source_device"],
        "timestamp": derive_track_timestamp(results, track, key),
        "model_id": _resolve_model_id(results),
        "family": track["final_prediction"]["family"],
        "genus": track["final_prediction"]["genus"],
        "species": track["final_prediction"]["species"],
        "family_confidence": track["final_prediction"]["family_confidence"],
        "genus_confidence": track["final_prediction"]["genus_confidence"],
        "species_confidence": track["final_prediction"]["species_confidence"],
        "num_detections": track["num_detections"],
        "s3_prefix": prefix,
        "composite_key": derive_composite_key(storage, bucket, prefix, track),
        "deployment_id": DEPLOYMENT_ID,
    }
    record = Track(**track_payload)
    return _model_dump(record)


def _build_classification_payload(
    storage: StorageAdapter,
    bucket: str,
    key: str,
    results: Dict[str, Any],
    track: Dict[str, Any],
    frame: Dict[str, Any],
    labels_cache: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    prefix = derive_s3_prefix(key)
    frame_number = int(frame["frame_number"])
    bbox = frame.get("bbox") or get_bbox_from_labels(storage, bucket, prefix, track, frame_number, labels_cache)
    if bbox is None:
        return None
    return {
        "device_id": results["source_device"],
        "timestamp": derive_frame_timestamp(results, track, frame, key),
        "track_id": derive_record_track_id(track, key),
        "model_id": _resolve_model_id(results),
        "image_key": derive_crop_key(storage, bucket, prefix, track, frame),
        "image_bucket": bucket,
        "family": frame["prediction"]["family"],
        "genus": frame["prediction"]["genus"],
        "species": frame["prediction"]["species"],
        "family_confidence": frame["prediction"]["family_confidence"],
        "genus_confidence": frame["prediction"]["genus_confidence"],
        "species_confidence": frame["prediction"]["species_confidence"],
        "frame_number": frame_number,
        "bounding_box": [float(value) for value in bbox],
    }


def _build_classification_records(
    storage: StorageAdapter,
    bucket: str,
    key: str,
    results: Dict[str, Any],
    track: Dict[str, Any],
    labels_cache: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    skipped_count = 0
    for frame in track.get("frames", []):
        try:
            classification_payload = _build_classification_payload(
                storage,
                bucket,
                key,
                results,
                track,
                frame,
                labels_cache,
            )
            if classification_payload is None:
                skipped_count += 1
                continue
            record = Classification(**classification_payload)
            records.append(_model_dump(record))
        except Exception as exc:
            skipped_count += 1
            log_s3_trigger(
                S3TriggerAction.FAILED,
                bucket,
                key,
                kind="classification",
                reason="validation_failed",
                track_id=track.get("track_id"),
                frame_number=frame.get("frame_number"),
                error=str(exc),
            )
            activity.record_classification_validation_failed(
                bucket,
                key,
                str(track.get("track_id")) if track.get("track_id") is not None else None,
                frame.get("frame_number"),
                str(exc),
            )
    return records, skipped_count


def _build_video_records(
    storage: StorageAdapter,
    bucket: str,
    key: str,
    results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    prefix = derive_s3_prefix(key)
    video_keys = storage.list_keys(bucket, prefix, suffix=".mp4")
    if not video_keys:
        return []
    if not (results.get("video_file") and results.get("video_info")):
        return []

    primary_key = f"{prefix}/{results['video_file']}"
    video_key = primary_key if storage.exists(bucket, primary_key) else video_keys[0]
    record = Video(
        device_id=results["source_device"],
        timestamp=results["video_timestamp"],
        video_key=video_key,
        video_bucket=bucket,
        s3_prefix=prefix,
        fps=results["video_info"]["fps"],
        total_frames=results["video_info"]["total_frames"],
        duration_seconds=results["video_info"]["duration_seconds"],
    )
    return [_model_dump(record)]


def _standalone_video_identity(video_key: str) -> Tuple[str, str, str]:
    """(device_id, timestamp, s3_prefix) for a video member, from its key alone.

    The capture directory is named after the video's stem; the device derives a
    video's ``video_timestamp`` from that same stem's first two underscore groups
    (``YYYYMMDD_HHMMSS``, microseconds dropped -- bugcam edge26 ``main.py``). We
    reproduce that exactly so a co-located ``results.json`` (which serves its
    ``video_timestamp``) enriches the same ``(device_id, timestamp)`` row instead
    of creating a second one.
    """
    prefix = video_key.rsplit("/", 1)[0]
    if prefix.rsplit("/", 1)[-1] == "videos":  # DOT layout: <capture>/videos/<file>.mp4
        prefix = prefix.rsplit("/", 1)[0]
    head, _, capture = prefix.rpartition("/")
    device_id = head.rsplit("/", 1)[-1]
    stem = capture.split("_")
    if not device_id or len(stem) < 2:
        raise ValueError(f"cannot derive video identity from key: {video_key!r}")
    timestamp = datetime.strptime(f"{stem[0]}_{stem[1]}", "%Y%m%d_%H%M%S").isoformat()
    return device_id, timestamp, prefix


def _build_standalone_video_record(bucket: str, video_key: str) -> Dict[str, Any]:
    device_id, timestamp, prefix = _standalone_video_identity(video_key)
    record = Video(
        device_id=device_id,
        timestamp=timestamp,
        video_key=video_key,
        video_bucket=bucket,
        s3_prefix=prefix,
    )
    return _model_dump(record)


def _parse_and_build_records(
    storage: StorageAdapter,
    bucket: str,
    key: str,
    *,
    version_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    try:
        results = storage.read_json(bucket, key, version_id=version_id, etag=etag)
    except ClientError:
        log_s3_trigger(S3TriggerAction.FAILED, bucket, key, kind="results", reason="read_failed")
        raise
    except Exception as exc:
        log_s3_trigger(S3TriggerAction.FAILED, bucket, key, kind="results", reason="malformed_json", error=str(exc))
        activity.record_results_malformed(bucket, key, str(exc))
        return [], [], [], [], {
            "input_tracks": 0,
            "skipped_tracks": 0,
            "skipped_classifications": 0,
            "composites_created": 0,
            "composites_skipped": 0,
            "composites_failed": 0,
        }

    manifest = _load_manifest(storage, bucket)
    labels_cache: Dict[str, Dict[str, Any]] = {}
    track_records: List[Dict[str, Any]] = []
    classification_records: List[Dict[str, Any]] = []
    confirmed_tracks = list(_iter_confirmed_tracks(results))
    stats = {
        "input_tracks": len(confirmed_tracks),
        "skipped_tracks": 0,
        "skipped_classifications": 0,
        "composites_created": 0,
        "composites_skipped": 0,
        "composites_failed": 0,
    }

    for track in confirmed_tracks:
        try:
            composite_result = ensure_track_composite(storage, bucket, key, track)
            if composite_result.status == CompositeStatus.CREATED:
                stats["composites_created"] += 1
            elif composite_result.reason and composite_result.reason is not CompositeSkipReason.EXISTS:
                stats["composites_skipped"] += 1
        except Exception as exc:
            log_s3_trigger(
                S3TriggerAction.FAILED,
                bucket,
                key,
                kind="composite",
                reason="generation_failed",
                track_id=track.get("track_id"),
                error=str(exc),
            )
            activity.record_composite_generation_failed(
                bucket,
                key,
                str(track.get("track_id")) if track.get("track_id") is not None else None,
                str(exc),
            )
            stats["composites_failed"] += 1

        try:
            track_records.append(_build_track_record(storage, bucket, key, results, track))
        except Exception as exc:
            log_s3_trigger(
                S3TriggerAction.FAILED,
                bucket,
                key,
                kind="track",
                reason="validation_failed",
                track_id=track.get("track_id"),
                error=str(exc),
            )
            activity.record_track_validation_failed(
                bucket,
                key,
                str(track.get("track_id")) if track.get("track_id") is not None else None,
                str(exc),
            )
            stats["skipped_tracks"] += 1
            continue
        records, skipped_count = _build_classification_records(storage, bucket, key, results, track, labels_cache)
        classification_records.extend(records)
        stats["skipped_classifications"] += skipped_count

    device_records = _resolve_devices(results, manifest)
    video_records = _build_video_records(storage, bucket, key, results)
    return track_records, classification_records, device_records, video_records, stats


def _write_records(
    writer: WriterProtocol,
    track_records: List[Dict[str, Any]],
    classification_records: List[Dict[str, Any]],
    device_records: List[Dict[str, Any]],
    video_records: List[Dict[str, Any]],
) -> None:
    writer.put_tracks(track_records)
    writer.put_classifications(classification_records)
    writer.put_devices_if_missing(device_records)
    writer.put_videos(video_records)


def process_results_object(
    storage: StorageAdapter,
    writer: WriterProtocol,
    bucket: str,
    key: str,
    *,
    version_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> Dict[str, int]:
    track_records, classification_records, device_records, video_records, stats = _parse_and_build_records(
        storage,
        bucket,
        key,
        version_id=version_id,
        etag=etag,
    )
    _write_records(writer, track_records, classification_records, device_records, video_records)
    print(f"Processed {len(track_records)} tracks, {len(classification_records)} classifications from {key}")
    return {
        "tracks": len(track_records),
        "classifications": len(classification_records),
        "devices": len(device_records),
        "videos": len(video_records),
        **stats,
    }


def process_heartbeat_object(
    storage: StorageAdapter,
    writer: WriterProtocol,
    bucket: str,
    key: str,
    *,
    version_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> Dict[str, int]:
    try:
        payload = storage.read_json(bucket, key, version_id=version_id, etag=etag)
        heartbeat_record = _model_dump(Heartbeat(**payload))
    except ClientError:
        raise
    except Exception as exc:
        print(f"Heartbeat validation failed for {key}: {exc}")
        return {"heartbeats": 0}
    writer.put_heartbeats([heartbeat_record])
    print(f"Processed 1 heartbeat from {key}")
    return {"heartbeats": 1}


def process_environment_object(
    storage: StorageAdapter,
    writer: WriterProtocol,
    bucket: str,
    key: str,
    *,
    version_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> Dict[str, int]:
    try:
        payload = storage.read_json(bucket, key, version_id=version_id, etag=etag)
        environment_record = _model_dump(EnvironmentalReading(**payload))
    except ClientError:
        raise
    except Exception as exc:
        print(f"Environment validation failed for {key}: {exc}")
        return {"environmental_readings": 0}
    writer.put_environmental_readings([environment_record])
    print(f"Processed 1 environmental reading from {key}")
    return {"environmental_readings": 1}


def process_video_object(
    storage: StorageAdapter,
    writer: WriterProtocol,
    bucket: str,
    key: str,
    *,
    version_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> Dict[str, int]:
    """A video uploaded flat (outside any archive) still gets a name-derived row,
    same identity derivation as an archived standalone video (_build_standalone_video_record)
    -- it just has no archive_key/byte-range stamp, so it serves from its flat key."""
    try:
        video_record = _build_standalone_video_record(bucket, key)
    except ValueError as exc:
        print(f"Video identity derivation failed for {key}: {exc}")
        return {"videos": 0}
    writer.put_videos([video_record])
    print(f"Processed 1 video from {key}")
    return {"videos": 1}


def _merge_summary(total: Dict[str, int], part: Dict[str, int]) -> None:
    for key, value in part.items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value


def process_archive_object(
    storage: StorageAdapter,
    writer: WriterProtocol,
    bucket: str,
    key: str,
    *,
    version_id: Optional[str] = None,
    etag: Optional[str] = None,
) -> Dict[str, int]:
    """Index an hourly batch tar in place: process its members without exploding.

    The media stays inside the archive; a tar-backed StorageAdapter feeds the
    existing per-object processors so the same DynamoDB rows are written, and an
    ArchiveIndexWriter stamps each row with the archive location + the member's
    byte range so serving can range-read. A single idempotency claim covers the
    whole archive (see process_s3_object); inner writes are deterministic upserts.
    """
    archive_bytes = storage.read_bytes(bucket, key)
    adapter = TarStorageAdapter(archive_bytes, storage)
    index_writer = ArchiveIndexWriter(writer, adapter, bucket, key)

    summary: Dict[str, int] = {"archives": 1, "result_objects": 0, "skipped_members": 0}
    results_names: List[str] = []
    json_object_names: List[str] = []
    video_names: List[str] = []
    for name in adapter.member_names():
        if name.endswith("/results.json"):
            results_names.append(name)
        elif name.endswith(VIDEO_MEMBER_SUFFIX):
            video_names.append(name)
        elif _processing_kind(name) in (ProcessingKind.HEARTBEAT, ProcessingKind.ENVIRONMENT):
            json_object_names.append(name)

    for name in sorted(results_names):
        try:
            _merge_summary(summary, process_results_object(adapter, index_writer, bucket, name))
            summary["result_objects"] += 1
        except Exception as exc:
            summary["skipped_members"] += 1
            log_s3_trigger(
                S3TriggerAction.FAILED, bucket, name, kind=ProcessingKind.RESULTS.value,
                reason="archive_member_failed", archive_key=key, error=str(exc),
            )

    # Standalone videos: any .mp4 a results.json above did not already emit. results
    # run first, so seen_video_keys covers co-located videos; the leftovers get a
    # name-derived, byte-range-stamped row here so every archived video is served.
    for name in sorted(video_names):
        if name in index_writer.seen_video_keys:
            continue
        try:
            index_writer.put_videos([_build_standalone_video_record(bucket, name)])
            summary["videos"] = summary.get("videos", 0) + 1
        except Exception as exc:
            summary["skipped_members"] += 1
            log_s3_trigger(
                S3TriggerAction.FAILED, bucket, name, kind="video",
                reason="archive_member_failed", archive_key=key, error=str(exc),
            )

    for name in sorted(json_object_names):
        member_kind = _processing_kind(name)
        try:
            if member_kind == ProcessingKind.HEARTBEAT:
                _merge_summary(summary, process_heartbeat_object(adapter, index_writer, bucket, name))
            else:
                _merge_summary(summary, process_environment_object(adapter, index_writer, bucket, name))
        except Exception as exc:
            summary["skipped_members"] += 1
            log_s3_trigger(
                S3TriggerAction.FAILED, bucket, name, kind=member_kind.value,
                reason="archive_member_failed", archive_key=key, error=str(exc),
            )

    return summary


def parse_s3_event(event: Dict[str, Any]) -> List[S3ObjectEvent]:
    records: List[S3ObjectEvent] = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        s3_object = record["s3"]["object"]
        key = unquote_plus(s3_object["key"])
        records.append(
            S3ObjectEvent(
                bucket=bucket,
                key=key,
                etag=s3_object.get("eTag"),
                version_id=s3_object.get("versionId"),
            )
        )
    return records


def _processing_status(summary: Dict[str, int]) -> str:
    if summary.get("skipped_duplicate", 0) > 0:
        return "duplicate"
    row_keys = {"tracks", "classifications", "devices", "videos", "heartbeats", "environmental_readings"}
    if any(summary.get(key, 0) > 0 for key in row_keys):
        if summary.get("composites_failed", 0) > 0:
            return "error"
        return "success"
    if any(summary.get(key, 0) > 0 for key in {"skipped_tracks", "skipped_classifications", "composites_failed"}):
        return "error"
    return "empty"


def _processing_kind(key: str) -> ProcessingKind:
    if key.startswith(ARCHIVE_KEY_PREFIX) and key.endswith(ARCHIVE_SUFFIXES):
        return ProcessingKind.ARCHIVE
    if key.endswith("/results.json"):
        return ProcessingKind.RESULTS
    if HEARTBEAT_KEY_PATTERN.match(key):
        return ProcessingKind.HEARTBEAT
    if ENVIRONMENT_KEY_PATTERN.match(key):
        return ProcessingKind.ENVIRONMENT
    if key.endswith(VIDEO_MEMBER_SUFFIX):
        return ProcessingKind.VIDEO
    return ProcessingKind.IGNORED


def _begin_idempotency(event: S3ObjectEvent, kind: ProcessingKind, store: ProcessedObjectStore) -> IdempotencyClaim:
    try:
        claim = store.begin(event, kind)
    except Exception as exc:
        log_s3_trigger(S3TriggerAction.IDEMPOTENCY_ERROR, event.bucket, event.key, kind=kind.value, error=str(exc))
        raise
    if claim.decision == IdempotencyDecision.UNAVAILABLE:
        log_s3_trigger(
            S3TriggerAction.IDEMPOTENCY_UNAVAILABLE,
            event.bucket,
            event.key,
            kind=kind.value,
            reason="missing_object_identity",
        )
    return claim


def _mark_idempotency_complete(
    event: S3ObjectEvent,
    kind: ProcessingKind,
    store: ProcessedObjectStore,
    claim: IdempotencyClaim,
) -> None:
    try:
        store.complete(event, claim)
    except Exception as exc:
        log_s3_trigger(S3TriggerAction.IDEMPOTENCY_ERROR, event.bucket, event.key, kind=kind.value, error=str(exc))
        raise


def _mark_idempotency_failed(
    event: S3ObjectEvent,
    kind: ProcessingKind,
    store: ProcessedObjectStore,
    claim: IdempotencyClaim,
) -> None:
    try:
        store.fail(event, claim)
    except Exception as exc:
        log_s3_trigger(S3TriggerAction.IDEMPOTENCY_ERROR, event.bucket, event.key, kind=kind.value, error=str(exc))
        raise


def process_s3_object(
    storage: StorageAdapter,
    writer: WriterProtocol,
    event: S3ObjectEvent,
    processed_store: ProcessedObjectStore,
) -> Dict[str, int]:
    kind = _processing_kind(event.key)
    log_s3_trigger(S3TriggerAction.RECEIVED, event.bucket, event.key, kind=kind.value)
    # Archives are the one supported object outside v1/: their members are v1 keys.
    if kind != ProcessingKind.ARCHIVE and not event.key.startswith("v1/"):
        log_s3_trigger(S3TriggerAction.IGNORED, event.bucket, event.key, reason="outside_v1_prefix")
        activity.record_object_ignored(event.bucket, event.key, activity.TriggerFailureReason.OUTSIDE_V1_PREFIX)
        return {}
    if kind == ProcessingKind.IGNORED:
        log_s3_trigger(S3TriggerAction.IGNORED, event.bucket, event.key, reason="unsupported_key")
        activity.record_object_ignored(event.bucket, event.key, activity.TriggerFailureReason.UNSUPPORTED_KEY)
        return {}
    claim = _begin_idempotency(event, kind, processed_store)
    if claim.decision == IdempotencyDecision.SKIP_DUPLICATE:
        summary = {"skipped_duplicate": 1}
        log_s3_trigger(S3TriggerAction.DUPLICATE, event.bucket, event.key, kind=kind.value, summary=summary)
        return summary
    if claim.decision == IdempotencyDecision.IN_FLIGHT:
        log_s3_trigger(S3TriggerAction.DUPLICATE, event.bucket, event.key, kind=kind.value, status="in_flight")
        raise RuntimeError(f"S3 object already processing: {event.key}")

    claimed = claim.decision == IdempotencyDecision.PROCESS and claim.attempt_id is not None
    try:
        activity.record_s3_received(event.bucket, event.key, kind.value)
        log_s3_trigger(S3TriggerAction.PROCESSING, event.bucket, event.key, kind=kind.value)
        if kind == ProcessingKind.ARCHIVE:
            summary = process_archive_object(
                storage,
                writer,
                event.bucket,
                event.key,
                version_id=event.version_id,
                etag=event.etag,
            )
        elif kind == ProcessingKind.RESULTS:
            summary = process_results_object(
                storage,
                writer,
                event.bucket,
                event.key,
                version_id=event.version_id,
                etag=event.etag,
            )
        elif kind == ProcessingKind.HEARTBEAT:
            summary = process_heartbeat_object(
                storage,
                writer,
                event.bucket,
                event.key,
                version_id=event.version_id,
                etag=event.etag,
            )
        elif kind == ProcessingKind.VIDEO:
            summary = process_video_object(
                storage,
                writer,
                event.bucket,
                event.key,
                version_id=event.version_id,
                etag=event.etag,
            )
        else:
            summary = process_environment_object(
                storage,
                writer,
                event.bucket,
                event.key,
                version_id=event.version_id,
                etag=event.etag,
            )
        status = _processing_status(summary)
        log_s3_trigger(S3TriggerAction.PROCESSED, event.bucket, event.key, kind=kind.value, status=status, summary=summary)
        activity.record_s3_processed(event.bucket, event.key, kind.value, status, summary)
    except Exception as exc:
        if claimed:
            try:
                _mark_idempotency_failed(event, kind, processed_store, claim)
            except Exception as cleanup_exc:
                log_s3_trigger(
                    S3TriggerAction.FAILED,
                    event.bucket,
                    event.key,
                    kind=kind.value,
                    error=str(exc),
                    cleanup_error=str(cleanup_exc),
                )
                raise cleanup_exc from exc
        log_s3_trigger(S3TriggerAction.FAILED, event.bucket, event.key, kind=kind.value, error=str(exc))
        raise

    if claimed:
        _mark_idempotency_complete(event, kind, processed_store, claim)
    return summary


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    storage = S3StorageAdapter()
    writer = DynamoWriter()
    processed_store = ProcessedObjectStore()
    summaries = []
    for s3_event in parse_s3_event(event):
        summary = process_s3_object(storage, writer, s3_event, processed_store)
        if summary:
            summaries.append(summary)
    return {"statusCode": 200, "body": json.dumps({"processed": summaries})}
