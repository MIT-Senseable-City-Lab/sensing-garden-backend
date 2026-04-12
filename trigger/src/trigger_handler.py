import json
import logging
import os
import re
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

import activity
from schemas import Classification, Device, EnvironmentalReading, Heartbeat, Track, Video


TRACKS_TABLE = os.environ.get("TRACKS_TABLE", "sensing-garden-tracks")
CLASSIFICATIONS_TABLE = os.environ.get("CLASSIFICATIONS_TABLE", "sensing-garden-classifications")
DEVICES_TABLE = os.environ.get("DEVICES_TABLE", "sensing-garden-devices")
VIDEOS_TABLE = os.environ.get("VIDEOS_TABLE", "sensing-garden-videos")
HEARTBEATS_TABLE = os.environ.get("HEARTBEATS_TABLE", "sensing-garden-heartbeats")
ENVIRONMENTAL_TABLE = os.environ.get("ENVIRONMENTAL_TABLE", "sensing-garden-environmental-readings")
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
    def read_text(self, bucket: str, key: str) -> str:
        raise NotImplementedError

    def read_json(self, bucket: str, key: str) -> Dict[str, Any]:
        return json.loads(self.read_text(bucket, key))

    def exists(self, bucket: str, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> List[str]:
        raise NotImplementedError


class S3StorageAdapter(StorageAdapter):
    def __init__(self):
        self.client = boto3.client("s3")

    def read_text(self, bucket: str, key: str) -> str:
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")

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
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def read_text(self, bucket: str, key: str) -> str:
        return self._path(key).read_text()

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
    short_id = track["track_id"][:8]
    timestamp = track.get("timestamp")
    candidates = [f"{s3_prefix}/composites/track_{short_id}.jpg"]
    if timestamp:
        candidates.append(f"{s3_prefix}/composites/{track['track_id']}_{timestamp}.jpg")
        candidates.append(f"{s3_prefix}/composites/{short_id}_{timestamp}.jpg")
    return candidates


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
    tracks = results.get("tracks", [])
    explicit = [track for track in tracks if track.get("confirmed") is True or track.get("is_confirmed") is True]
    return explicit or tracks


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


def _parse_and_build_records(
    storage: StorageAdapter,
    bucket: str,
    key: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    try:
        results = storage.read_json(bucket, key)
    except Exception as exc:
        log_s3_trigger(S3TriggerAction.FAILED, bucket, key, kind="results", reason="malformed_json", error=str(exc))
        return [], [], [], [], {"input_tracks": 0, "skipped_tracks": 0, "skipped_classifications": 0}

    manifest = _load_manifest(storage, bucket)
    labels_cache: Dict[str, Dict[str, Any]] = {}
    track_records: List[Dict[str, Any]] = []
    classification_records: List[Dict[str, Any]] = []
    confirmed_tracks = list(_iter_confirmed_tracks(results))
    stats = {
        "input_tracks": len(confirmed_tracks),
        "skipped_tracks": 0,
        "skipped_classifications": 0,
    }

    for track in confirmed_tracks:
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


def process_results_object(storage: StorageAdapter, writer: WriterProtocol, bucket: str, key: str) -> Dict[str, int]:
    track_records, classification_records, device_records, video_records, stats = _parse_and_build_records(
        storage,
        bucket,
        key,
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


def process_heartbeat_object(storage: StorageAdapter, writer: WriterProtocol, bucket: str, key: str) -> Dict[str, int]:
    try:
        payload = storage.read_json(bucket, key)
        heartbeat_record = _model_dump(Heartbeat(**payload))
    except Exception as exc:
        print(f"Heartbeat validation failed for {key}: {exc}")
        return {"heartbeats": 0}
    writer.put_heartbeats([heartbeat_record])
    print(f"Processed 1 heartbeat from {key}")
    return {"heartbeats": 1}


def process_environment_object(storage: StorageAdapter, writer: WriterProtocol, bucket: str, key: str) -> Dict[str, int]:
    try:
        payload = storage.read_json(bucket, key)
        environment_record = _model_dump(EnvironmentalReading(**payload))
    except Exception as exc:
        print(f"Environment validation failed for {key}: {exc}")
        return {"environmental_readings": 0}
    writer.put_environmental_readings([environment_record])
    print(f"Processed 1 environmental reading from {key}")
    return {"environmental_readings": 1}


def parse_s3_event(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    records: List[Tuple[str, str]] = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        records.append((bucket, key))
    return records


def _processing_status(summary: Dict[str, int]) -> str:
    row_keys = {"tracks", "classifications", "devices", "videos", "heartbeats", "environmental_readings"}
    if any(summary.get(key, 0) > 0 for key in row_keys):
        return "success"
    if any(summary.get(key, 0) > 0 for key in {"skipped_tracks", "skipped_classifications"}):
        return "error"
    return "empty"


def _processing_kind(key: str) -> str:
    if key.endswith("/results.json"):
        return "results"
    if HEARTBEAT_KEY_PATTERN.match(key):
        return "heartbeat"
    if ENVIRONMENT_KEY_PATTERN.match(key):
        return "environment"
    return "ignored"


def process_s3_object(storage: StorageAdapter, writer: WriterProtocol, bucket: str, key: str) -> Dict[str, int]:
    kind = _processing_kind(key)
    log_s3_trigger(S3TriggerAction.RECEIVED, bucket, key, kind=kind)
    if not key.startswith("v1/"):
        log_s3_trigger(S3TriggerAction.IGNORED, bucket, key, reason="outside_v1_prefix")
        return {}
    if kind == "ignored":
        log_s3_trigger(S3TriggerAction.IGNORED, bucket, key, reason="unsupported_key")
        return {}

    log_s3_trigger(S3TriggerAction.PROCESSING, bucket, key, kind=kind)
    try:
        if kind == "results":
            summary = process_results_object(storage, writer, bucket, key)
        elif kind == "heartbeat":
            summary = process_heartbeat_object(storage, writer, bucket, key)
        else:
            summary = process_environment_object(storage, writer, bucket, key)
    except Exception as exc:
        log_s3_trigger(S3TriggerAction.FAILED, bucket, key, kind=kind, error=str(exc))
        raise

    status = _processing_status(summary)
    log_s3_trigger(S3TriggerAction.PROCESSED, bucket, key, kind=kind, status=status, summary=summary)
    activity.record_s3_processed(bucket, key, status, summary)
    return summary


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    storage = S3StorageAdapter()
    writer = DynamoWriter()
    summaries = []
    for bucket, key in parse_s3_event(event):
        summary = process_s3_object(storage, writer, bucket, key)
        if summary:
            summaries.append(summary)
    return {"statusCode": 200, "body": json.dumps({"processed": summaries})}
