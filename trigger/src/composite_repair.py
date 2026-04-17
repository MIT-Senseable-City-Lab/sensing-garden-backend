from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Protocol

import boto3
from boto3.dynamodb.conditions import Attr
from pydantic import BaseModel

from composites import (
    CompositeResult,
    CompositeSkipReason,
    CompositeSource,
    CompositeStatus,
    CompositeStorage,
    candidate_composite_keys,
    derive_s3_prefix,
    ensure_track_composite,
    iter_result_tracks,
)
from trigger_handler import derive_record_track_id


class RepairStatus(str, Enum):
    ALREADY_CORRECT = "already_correct"
    UPDATE = "update"
    MISSING_COMPOSITE = "missing_composite"
    MISSING_TRACK = "missing_track"

    @classmethod
    def from_state(
        cls,
        track: Optional["TrackSnapshot"],
        expected_exists: bool,
        expected_composite_key: str,
    ) -> "RepairStatus":
        if track is None:
            return cls.MISSING_TRACK
        if not expected_exists:
            return cls.MISSING_COMPOSITE
        if track.composite_key == expected_composite_key:
            return cls.ALREADY_CORRECT
        return cls.UPDATE


class ApplyStatus(str, Enum):
    UPDATED = "updated"
    SKIPPED = "skipped"


class TrackSnapshot(BaseModel):
    device_id: str
    track_id: str
    composite_key: Optional[str] = None


class PrefixBackfillResult(BaseModel):
    device_id: str
    track_id: str
    composite_key: str
    composite_status: CompositeStatus
    update_status: ApplyStatus
    reason: Optional[CompositeSkipReason] = None


class RepairManifestRow(BaseModel):
    device_id: str
    track_id: str
    s3_prefix: str
    current_composite_key: Optional[str]
    expected_composite_key: str
    status: RepairStatus


class RepairManifest(BaseModel):
    bucket: str
    results_key: str
    rows: list[RepairManifestRow]


class RepairApplyResult(BaseModel):
    device_id: str
    track_id: str
    expected_composite_key: str
    status: ApplyStatus


class RepairStorage(Protocol):
    def read_json(self, bucket: str, key: str) -> dict[str, Any]:
        ...

    def exists(self, bucket: str, key: str) -> bool:
        ...


class TrackStore(Protocol):
    def get_track(self, device_id: str, track_id: str) -> Optional[TrackSnapshot]:
        ...

    def update_composite_key(self, device_id: str, track_id: str, composite_key: str) -> None:
        ...


class PrefixTrackStore(TrackStore, Protocol):
    def list_tracks_by_prefix(self, prefix: str) -> list[TrackSnapshot]:
        ...


class DynamoTrackStore:
    def __init__(self, table_name: str = "sensing-garden-tracks") -> None:
        self.table = boto3.resource("dynamodb").Table(table_name)

    def get_track(self, device_id: str, track_id: str) -> Optional[TrackSnapshot]:
        response = self.table.get_item(Key={"track_id": track_id, "device_id": device_id})
        item = response.get("Item")
        if item is None:
            return None
        return TrackSnapshot(
            device_id=str(item["device_id"]),
            track_id=str(item["track_id"]),
            composite_key=item.get("composite_key"),
        )

    def update_composite_key(self, device_id: str, track_id: str, composite_key: str) -> None:
        self.table.update_item(
            Key={"track_id": track_id, "device_id": device_id},
            UpdateExpression="SET composite_key = :composite_key",
            ConditionExpression="attribute_exists(track_id) AND attribute_exists(device_id)",
            ExpressionAttributeValues={":composite_key": composite_key},
        )

    def list_tracks_by_prefix(self, prefix: str) -> list[TrackSnapshot]:
        tracks: list[TrackSnapshot] = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("s3_prefix").eq(prefix),
            "ProjectionExpression": "device_id, track_id, composite_key",
        }
        while True:
            response = self.table.scan(**scan_kwargs)
            tracks.extend(
                TrackSnapshot(
                    device_id=str(item["device_id"]),
                    track_id=str(item["track_id"]),
                    composite_key=item.get("composite_key"),
                )
                for item in response.get("Items", [])
            )
            last_key = response.get("LastEvaluatedKey")
            if last_key is None:
                return tracks
            scan_kwargs["ExclusiveStartKey"] = last_key


def build_repair_manifest(
    storage: RepairStorage,
    track_store: TrackStore,
    bucket: str,
    results_key: str,
) -> RepairManifest:
    if CompositeSource.from_results_key(results_key) is not CompositeSource.DOT:
        raise ValueError(f"repair only supports DOT results keys: {results_key}")

    results = storage.read_json(bucket, results_key)
    device_id = str(results["source_device"])
    s3_prefix = derive_s3_prefix(results_key)
    rows = [
        _repair_row(storage, track_store, bucket, results_key, s3_prefix, device_id, track)
        for track in iter_result_tracks(results)
    ]
    return RepairManifest(bucket=bucket, results_key=results_key, rows=rows)


def apply_repair_manifest(track_store: TrackStore, manifest: RepairManifest) -> list[RepairApplyResult]:
    return [_apply_repair_row(track_store, row) for row in manifest.rows]


def backfill_dynamo_prefix(
    storage: CompositeStorage,
    track_store: PrefixTrackStore,
    bucket: str,
    prefix: str,
    overwrite_existing: bool,
) -> list[PrefixBackfillResult]:
    if CompositeSource.from_results_key(f"{prefix}/results.json") is not CompositeSource.DOT:
        raise ValueError(f"dynamo prefix backfill only supports DOT prefixes: {prefix}")
    return [
        _backfill_dynamo_track(storage, track_store, bucket, prefix, track, overwrite_existing)
        for track in track_store.list_tracks_by_prefix(prefix)
    ]


def _repair_row(
    storage: RepairStorage,
    track_store: TrackStore,
    bucket: str,
    results_key: str,
    s3_prefix: str,
    device_id: str,
    track: dict[str, Any],
) -> RepairManifestRow:
    track_id = derive_record_track_id(track, results_key)
    expected_key = candidate_composite_keys(s3_prefix, track)[0]
    track_snapshot = track_store.get_track(device_id, track_id)
    status = RepairStatus.from_state(track_snapshot, storage.exists(bucket, expected_key), expected_key)
    return RepairManifestRow(
        device_id=device_id,
        track_id=track_id,
        s3_prefix=s3_prefix,
        current_composite_key=track_snapshot.composite_key if track_snapshot else None,
        expected_composite_key=expected_key,
        status=status,
    )


def _backfill_dynamo_track(
    storage: CompositeStorage,
    track_store: PrefixTrackStore,
    bucket: str,
    prefix: str,
    track: TrackSnapshot,
    overwrite_existing: bool,
) -> PrefixBackfillResult:
    composite = ensure_track_composite(
        storage,
        bucket,
        f"{prefix}/results.json",
        _dot_track_payload(storage, bucket, prefix, track),
        overwrite_existing,
    )
    should_update = storage.exists(bucket, composite.composite_key) and track.composite_key != composite.composite_key
    if should_update:
        track_store.update_composite_key(track.device_id, track.track_id, composite.composite_key)
    return _prefix_backfill_result(track, composite, should_update)


def _dot_track_payload(
    storage: CompositeStorage,
    bucket: str,
    prefix: str,
    track: TrackSnapshot,
) -> dict[str, str]:
    if "_" in track.track_id:
        return _timestamped_dot_track_payload(track.track_id)
    crop_prefix = f"{prefix}/crops/{track.track_id}_"
    crop_keys = storage.list_keys(bucket, crop_prefix, suffix=".jpg")
    if not crop_keys:
        raise ValueError(f"missing DOT crop folder for track id: {track.track_id}")
    crop_folders = sorted({key.split("/crops/", 1)[1].split("/", 1)[0] for key in crop_keys})
    if len(crop_folders) != 1:
        raise ValueError(f"ambiguous DOT crop folders for track id: {track.track_id}")
    return _timestamped_dot_track_payload(crop_folders[0])


def _timestamped_dot_track_payload(track_id_with_timestamp: str) -> dict[str, str]:
    track_id, timestamp = track_id_with_timestamp.rsplit("_", 1)
    if not track_id or not timestamp:
        raise ValueError(f"invalid DOT track id: {track_id_with_timestamp}")
    return {"track_id": track_id, "timestamp": timestamp}


def _prefix_backfill_result(
    track: TrackSnapshot,
    composite: CompositeResult,
    did_update: bool,
) -> PrefixBackfillResult:
    return PrefixBackfillResult(
        device_id=track.device_id,
        track_id=track.track_id,
        composite_key=composite.composite_key,
        composite_status=composite.status,
        update_status=ApplyStatus.UPDATED if did_update else ApplyStatus.SKIPPED,
        reason=composite.reason,
    )


def _apply_repair_row(track_store: TrackStore, row: RepairManifestRow) -> RepairApplyResult:
    if row.status is RepairStatus.UPDATE:
        track_store.update_composite_key(row.device_id, row.track_id, row.expected_composite_key)
        status = ApplyStatus.UPDATED
    else:
        status = ApplyStatus.SKIPPED
    return RepairApplyResult(
        device_id=row.device_id,
        track_id=row.track_id,
        expected_composite_key=row.expected_composite_key,
        status=status,
    )
