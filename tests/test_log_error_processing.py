from __future__ import annotations

import io
import json
import os
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

import log_scan  # noqa: E402
import trigger_handler  # noqa: E402
from monitor_config import MonitorConfig  # noqa: E402
from monitoring import Monitoring  # noqa: E402
from notify import Notification, Notifier  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)

from test_monitoring import FakeStateStore, RecordingChannel  # noqa: E402

NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)

CLEAN_LOG = """\
12:00:01 | INFO     | pipeline started
12:00:02 | WARNING  | slow flush
STATUS: recorder=alive detection=alive
"""

ERROR_LOG = """\
12:00:01 | INFO     | pipeline started
12:00:02 | ERROR    | camera read failed: timeout
Traceback (most recent call last):
  File "x.py", line 1, in run
RuntimeError: boom
12:00:05 | CRITICAL | detection worker died
12:00:09 | INFO     | recovered
"""


class TestLogScan:
    def test_clean_log_has_no_errors(self):
        digest = log_scan.scan(CLEAN_LOG.splitlines(), device_id="FLIK1", log_name="edge26_20260713.log")
        assert digest.error_count == 0 and digest.traceback_count == 0

    def test_counts_error_levels_and_tracebacks_without_double_counting(self):
        digest = log_scan.scan(ERROR_LOG.splitlines(), device_id="FLIK1", log_name="edge26_20260713.log")
        assert digest.error_count == 2  # ERROR + CRITICAL lines; traceback not re-counted
        assert digest.traceback_count == 1
        assert "camera read failed" in digest.first_error
        assert "detection worker died" in digest.last_error

    def test_raw_traceback_only_still_counts(self):
        lines = ["Traceback (most recent call last):", "  File ...", "ValueError: x"]
        digest = log_scan.scan(lines, device_id="FLIK1", log_name="l.log")
        assert digest.error_count == 1 and digest.traceback_count == 1

    def test_message_containing_level_word_is_not_an_error(self):
        lines = ["12:00:01 | INFO     | retried after ERROR in previous run"]
        digest = log_scan.scan(lines, device_id="FLIK1", log_name="l.log")
        assert digest.error_count == 0

    def test_parse_log_key(self):
        assert log_scan.parse_log_key("v1/FLIK1/logs/edge26_20260713.log") == ("FLIK1", "edge26_20260713.log")
        assert log_scan.parse_log_key("v1/FLIK1/heartbeats/x.json") is None
        assert log_scan.parse_log_key("v1/FLIK1/logs/nested/x.log") is None


class RecordingMonitor:
    def __init__(self):
        self.digests = []
        self.heartbeats = []
        self.capture_reports = []

    def on_log_digest(self, digest):
        self.digests.append(digest)

    def on_heartbeat(self, record):
        self.heartbeats.append(record)

    def on_capture_report(self, record):
        self.capture_reports.append(record)


class TestProcessLogObject:
    def _write(self, root: Path, key: str, content: str) -> None:
        target = root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def test_flat_log_scanned_and_digest_delivered(self, tmp_path):
        key = "v1/FLIK1/logs/edge26_20260713.log"
        self._write(tmp_path, key, ERROR_LOG)
        monitor = RecordingMonitor()
        summary = trigger_handler.process_log_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            key,
            monitor=monitor,
        )
        assert summary == {"logs": 1, "log_error_lines": 2}
        (digest,) = monitor.digests
        assert digest.device_id == "FLIK1" and digest.error_count == 2

    def test_clean_log_produces_no_digest(self, tmp_path):
        key = "v1/FLIK1/logs/edge26_20260713.log"
        self._write(tmp_path, key, CLEAN_LOG)
        monitor = RecordingMonitor()
        summary = trigger_handler.process_log_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            key,
            monitor=monitor,
        )
        assert summary["logs"] == 1 and monitor.digests == []

    def test_monitor_failure_does_not_fail_processing(self, tmp_path):
        class Exploding:
            def on_log_digest(self, digest):
                raise RuntimeError("boom")

        key = "v1/FLIK1/logs/edge26_20260713.log"
        self._write(tmp_path, key, ERROR_LOG)
        summary = trigger_handler.process_log_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            key,
            monitor=Exploding(),
        )
        assert summary["logs"] == 1

    def test_processing_kind_recognizes_logs(self):
        assert trigger_handler._processing_kind("v1/FLIK1/logs/edge26_20260713.log") == trigger_handler.ProcessingKind.LOG
        assert trigger_handler._processing_kind("v1/FLIK1/logs/notes.txt") == trigger_handler.ProcessingKind.IGNORED

    def test_archive_member_log_is_scanned(self, tmp_path):
        member_key = "v1/FLIK1/logs/edge26_20260713.log"
        archive_key = "v2/archives/FLIK1/20260713_120000.tar"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            data = ERROR_LOG.encode("utf-8")
            info = tarfile.TarInfo(name=member_key)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        target = tmp_path / archive_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(buffer.getvalue())

        monitor = RecordingMonitor()
        summary = trigger_handler.process_archive_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            archive_key,
            monitor=monitor,
        )
        assert summary["logs"] == 1
        (digest,) = monitor.digests
        assert digest.error_count == 2

    def test_archive_member_heartbeat_reaches_monitor(self, tmp_path):
        """A heartbeat shipped bundled in an archive (not the device's primary
        path -- heartbeats are a priority kind that ship individually -- but a
        real fallback) must still run content checks, same as a standalone
        heartbeat upload. process_archive_object's json-member loop was calling
        process_heartbeat_object without monitor=, so this silently never fired."""
        member_key = "v1/FLIK1/heartbeats/20260713_120000.json"
        archive_key = "v2/archives/FLIK1/20260713_120000.tar"
        payload = json.dumps({
            "device_id": "FLIK1", "timestamp": NOW.isoformat(),
            "cpu_temperature_celsius": 40.0, "storage_free_bytes": 50 * 1024**3,
            "storage_total_bytes": 100 * 1024**3, "uptime_seconds": 3600.0,
        }).encode("utf-8")
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo(name=member_key)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        target = tmp_path / archive_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(buffer.getvalue())

        monitor = RecordingMonitor()
        summary = trigger_handler.process_archive_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            archive_key,
            monitor=monitor,
        )
        assert summary["heartbeats"] == 1
        (record,) = monitor.heartbeats
        assert record["device_id"] == "FLIK1"

    def test_archive_member_capture_report_reaches_monitor(self, tmp_path):
        """Capture (sampling-effort) reports ride the tar with --archive-batch
        (capture_report.py: 'each one lands in the per-device tar next to the
        results it describes'), so this is their only real delivery path in
        production -- process_archive_object's member classifier previously
        had no branch for ProcessingKind.CAPTURE at all, so every capture
        report shipped this way was silently dropped."""
        member_key = "v1/FLIK1/captures/20260713_120000.json"
        archive_key = "v2/archives/FLIK1/20260713_120000.tar"
        payload = json.dumps({
            "device_id": "FLIK1",
            "period_start": "2026-07-13T11:00:00+00:00",
            "period_end": "2026-07-13T12:00:00+00:00",
            "sample_count": 3,
            "total_duration_seconds": 90.0,
        }).encode("utf-8")
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo(name=member_key)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        target = tmp_path / archive_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(buffer.getvalue())

        monitor = RecordingMonitor()
        summary = trigger_handler.process_archive_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            archive_key,
            monitor=monitor,
        )
        assert summary["capture_reports"] == 1
        (record,) = monitor.capture_reports
        assert record["device_id"] == "FLIK1"
        assert record["sample_count"] == 3


class TestOnLogDigest:
    def _monitoring(self, cfg=None, now=NOW):
        store = FakeStateStore()
        channel = RecordingChannel()
        clock = {"now": now}
        mon = Monitoring(
            cfg=cfg or MonitorConfig(),
            state_store=store,
            notifier=Notifier([channel]),
            roster_fn=lambda: [{"device_id": "FLIK1", "liveness_enabled": True}],
            latest_heartbeats_fn=lambda ids: {},
            now_fn=lambda: clock["now"],
        )
        return mon, store, channel, clock

    def _digest(self, **kw):
        defaults = dict(device_id="FLIK1", log_name="edge26_20260713.log",
                        error_count=3, traceback_count=1,
                        first_error="12:00 | ERROR | a", last_error="12:05 | ERROR | b")
        defaults.update(kw)
        return log_scan.ErrorDigest(**defaults)

    def test_notifies_once_per_cooldown_window(self):
        mon, store, channel, clock = self._monitoring()
        mon.on_log_digest(self._digest())
        mon.on_log_digest(self._digest(log_name="edge26_20260714.log"))
        assert len(channel.sent) == 1
        assert "3 error line(s)" in channel.sent[0].title
        assert channel.sent[0].route == "emergency"

        clock["now"] = NOW + timedelta(seconds=MonitorConfig().log_error_cooldown_seconds + 60)
        mon.on_log_digest(self._digest(log_name="edge26_20260715.log"))
        assert len(channel.sent) == 2

    def test_unmonitored_device_is_silent(self):
        mon, store, channel, clock = self._monitoring()
        mon.on_log_digest(self._digest(device_id="GHOST"))
        assert channel.sent == []
