from __future__ import annotations

import io
import json
import os
import sys
import tarfile
from pathlib import Path

import pytest


os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

import trigger_handler  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)


BUCKET = "bucket-1"
ARCHIVE_KEY = "v2/archives/FLIK4/20260625_150000.tar"


def _make_tar(members: dict[str, bytes]) -> bytes:
    """Uncompressed tar so each member's byte range is valid in the raw archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, body in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


class _ArchiveStorage:
    """Serves the archive bytes for read_bytes; empty S3 fallback for everything else."""

    def __init__(self, archive_bytes: bytes) -> None:
        self._archive_bytes = archive_bytes
        self.objects: dict[str, bytes] = {}

    def read_bytes(self, bucket: str, key: str) -> bytes:
        return self._archive_bytes

    def read_text(self, bucket, key, *, version_id=None, etag=None) -> str:
        return self.objects[key].decode("utf-8")

    def read_json(self, bucket, key, *, version_id=None, etag=None):
        return json.loads(self.read_text(bucket, key))

    def write_bytes(self, bucket, key, body, content_type) -> None:
        self.objects[key] = body

    def exists(self, bucket, key) -> bool:
        return key in self.objects

    def list_keys(self, bucket, prefix, suffix="") -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix) and k.endswith(suffix))


def _process(members: dict[str, bytes]):
    archive_bytes = _make_tar(members)
    storage = _ArchiveStorage(archive_bytes)
    writer = trigger_handler.CollectingWriter()
    summary = trigger_handler.process_archive_object(storage, writer, BUCKET, ARCHIVE_KEY)
    return archive_bytes, writer, summary


# --- E6: the name derivation must equal the device's video_timestamp derivation ---

def test_standalone_video_identity_matches_device_derivation():
    dev, ts, prefix = trigger_handler._standalone_video_identity(
        "v1/FLIK4/20260625_141636/video.mp4"
    )
    assert dev == "FLIK4"
    assert ts == "2026-06-25T14:16:36"  # strptime("20260625_141636", "%Y%m%d_%H%M%S").isoformat()
    assert prefix == "v1/FLIK4/20260625_141636"


def test_standalone_video_identity_dot_layout_and_dropped_micros():
    # DOT videos live under a videos/ subdir; the capture dir still owns the timestamp.
    dev, ts, prefix = trigger_handler._standalone_video_identity(
        "v1/DOT9/20260625_141636/videos/clip.mp4"
    )
    assert (dev, ts, prefix) == ("DOT9", "2026-06-25T14:16:36", "v1/DOT9/20260625_141636")
    # microseconds in the capture stem are dropped, exactly as the device does.
    _, ts_micros, _ = trigger_handler._standalone_video_identity(
        "v1/FLIK4/20260625_141636_427099/video.mp4"
    )
    assert ts_micros == "2026-06-25T14:16:36"


# --- E1 (spec's failable test): a video-only archive still maps the video ---

def test_archive_video_only_member_is_mapped():
    video_bytes = b"\x00\x01FAKE-MP4-PAYLOAD\x02\x03"
    key = "v1/FLIK4/20260625_141636/video.mp4"
    archive_bytes, writer, summary = _process({key: video_bytes})

    assert len(writer.videos) == 1
    row = writer.videos[0]
    assert row["device_id"] == "FLIK4"
    assert row["timestamp"] == "2026-06-25T14:16:36"
    assert row["video_key"] == key
    assert row["video_bucket"] == BUCKET
    assert row["archive_bucket"] == BUCKET
    assert row["archive_key"] == ARCHIVE_KEY
    off, size = row["video_offset"], row["video_size"]
    assert archive_bytes[off:off + size] == video_bytes
    assert summary["videos"] == 1


# --- E3: co-located results.json + video -> one enriched row, no duplicate ---

def test_archive_colocated_results_video_is_single_enriched_row():
    prefix = "v1/FLIK4/20260625_141636"
    video_bytes = b"CO-LOCATED-MP4"
    results = {
        "source_device": "FLIK4",
        "video_file": "video.mp4",
        "video_timestamp": "2026-06-25T14:16:36",
        "video_info": {"fps": 30, "total_frames": 300, "duration_seconds": 10.0},
        "tracks": [],
    }
    members = {
        f"{prefix}/video.mp4": video_bytes,
        f"{prefix}/results.json": json.dumps(results).encode("utf-8"),
    }
    archive_bytes, writer, summary = _process(members)

    assert len(writer.videos) == 1  # not duplicated by the standalone pass
    row = writer.videos[0]
    assert row["timestamp"] == "2026-06-25T14:16:36"
    assert row["fps"] == 30  # enriched from results.json
    off, size = row["video_offset"], row["video_size"]
    assert archive_bytes[off:off + size] == video_bytes  # still byte-range mapped


# --- an undecodable capture stem is skipped, not fatal ---

def test_archive_video_with_underivable_timestamp_is_skipped():
    # Capture segment lacks a HHMMSS group -> cannot match the device derivation.
    key = "v1/DOTX/20260625/videos/clip.mp4"
    _archive, writer, summary = _process({key: b"x"})
    assert writer.videos == []
    assert summary["skipped_members"] == 1
