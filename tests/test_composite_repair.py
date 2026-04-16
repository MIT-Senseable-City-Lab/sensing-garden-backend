from __future__ import annotations

import json
import sys
from pathlib import Path


TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

from composite_repair import (  # noqa: E402
    ApplyStatus,
    RepairManifest,
    RepairManifestRow,
    RepairStatus,
    TrackSnapshot,
    apply_repair_manifest,
    build_repair_manifest,
)

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)


class FakeStorage:
    def __init__(self, payloads: dict[str, dict[str, object]], existing_keys: set[str]) -> None:
        self.payloads = payloads
        self.existing_keys = existing_keys

    def read_json(self, bucket: str, key: str) -> dict[str, object]:
        return self.payloads[key]

    def exists(self, bucket: str, key: str) -> bool:
        return key in self.existing_keys


class FakeTrackStore:
    def __init__(self, tracks: dict[tuple[str, str], TrackSnapshot]) -> None:
        self.tracks = tracks
        self.updates: list[tuple[str, str, str]] = []

    def get_track(self, device_id: str, track_id: str) -> TrackSnapshot | None:
        return self.tracks.get((device_id, track_id))

    def update_composite_key(self, device_id: str, track_id: str, composite_key: str) -> None:
        self.updates.append((device_id, track_id, composite_key))


def _results_key() -> str:
    return "v1/FLIK2-dot01/20260416/results.json"


def _payload() -> dict[str, object]:
    return {
        "source_device": "FLIK2-dot01",
        "date": "20260416",
        "tracks": [
            {"track_id": "99533", "timestamp": "154110"},
            {"track_id": "99534", "timestamp": "154111"},
            {"track_id": "99535", "timestamp": "154112"},
            {"track_id": "99536", "timestamp": "154113"},
        ],
    }


def test_repair_manifest_marks_update_correct_missing_composite_and_missing_track() -> None:
    expected_99533 = "v1/FLIK2-dot01/20260416/composites/99533_154110.jpg"
    expected_99534 = "v1/FLIK2-dot01/20260416/composites/99534_154111.jpg"
    expected_99536 = "v1/FLIK2-dot01/20260416/composites/99536_154113.jpg"
    storage = FakeStorage(
        {_results_key(): _payload()},
        {expected_99533, expected_99534, expected_99536},
    )
    track_store = FakeTrackStore(
        {
            ("FLIK2-dot01", "99533_154110"): TrackSnapshot(
                device_id="FLIK2-dot01",
                track_id="99533_154110",
                composite_key="v1/FLIK2-dot01/20260416/composites/track_99533.jpg",
            ),
            ("FLIK2-dot01", "99534_154111"): TrackSnapshot(
                device_id="FLIK2-dot01",
                track_id="99534_154111",
                composite_key=expected_99534,
            ),
            ("FLIK2-dot01", "99535_154112"): TrackSnapshot(
                device_id="FLIK2-dot01",
                track_id="99535_154112",
                composite_key="v1/FLIK2-dot01/20260416/composites/track_99535.jpg",
            ),
        }
    )

    manifest = build_repair_manifest(storage, track_store, "bucket", _results_key())

    statuses = {row.track_id: row.status for row in manifest.rows}
    assert statuses == {
        "99533_154110": RepairStatus.UPDATE,
        "99534_154111": RepairStatus.ALREADY_CORRECT,
        "99535_154112": RepairStatus.MISSING_COMPOSITE,
        "99536_154113": RepairStatus.MISSING_TRACK,
    }
    assert manifest.rows[0].expected_composite_key == expected_99533


def test_apply_repair_manifest_updates_only_update_rows() -> None:
    track_store = FakeTrackStore({})
    manifest = RepairManifest(
        bucket="bucket",
        results_key=_results_key(),
        rows=[
            RepairManifestRow(
                device_id="FLIK2-dot01",
                track_id="99533_154110",
                s3_prefix="v1/FLIK2-dot01/20260416",
                current_composite_key="v1/FLIK2-dot01/20260416/composites/track_99533.jpg",
                expected_composite_key="v1/FLIK2-dot01/20260416/composites/99533_154110.jpg",
                status=RepairStatus.UPDATE,
            ),
            RepairManifestRow(
                device_id="FLIK2-dot01",
                track_id="99534_154111",
                s3_prefix="v1/FLIK2-dot01/20260416",
                current_composite_key="v1/FLIK2-dot01/20260416/composites/99534_154111.jpg",
                expected_composite_key="v1/FLIK2-dot01/20260416/composites/99534_154111.jpg",
                status=RepairStatus.ALREADY_CORRECT,
            ),
        ],
    )

    results = apply_repair_manifest(track_store, manifest)

    assert track_store.updates == [
        (
            "FLIK2-dot01",
            "99533_154110",
            "v1/FLIK2-dot01/20260416/composites/99533_154110.jpg",
        )
    ]
    assert [result.status for result in results] == [ApplyStatus.UPDATED, ApplyStatus.SKIPPED]


def test_repair_manifest_json_round_trips() -> None:
    manifest = RepairManifest(
        bucket="bucket",
        results_key=_results_key(),
        rows=[
            RepairManifestRow(
                device_id="FLIK2-dot01",
                track_id="99533_154110",
                s3_prefix="v1/FLIK2-dot01/20260416",
                current_composite_key=None,
                expected_composite_key="v1/FLIK2-dot01/20260416/composites/99533_154110.jpg",
                status=RepairStatus.UPDATE,
            )
        ],
    )

    restored = RepairManifest.model_validate_json(json.dumps(manifest.model_dump(mode="json")))

    assert restored == manifest
