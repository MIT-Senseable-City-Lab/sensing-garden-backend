from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

import trigger_handler  # noqa: E402
from monitor_config import MonitorConfig  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)

from test_monitoring import _monitoring  # noqa: E402

REPORT = {
    "device_id": "FLIK1",
    "period_start": "2026-07-14T11:00:00+00:00",
    "period_end": "2026-07-14T12:00:00+00:00",
    "sample_count": 42,
    "total_duration_seconds": 1260.0,
    "samples": [{"video_file": "x.mp4", "duration_seconds": 30.0, "size_bytes": 1000}],
}


class TestOnCaptureReport:
    """Informational, always sends -- no OK/BAD episode, no cooldown, same as
    digest(). Never touches S3: the file the report describes is left exactly
    where CaptureLog/Pollen already put it."""

    def test_sends_summary_on_general_route(self):
        mon, _, channel = _monitoring(roster=[{"device_id": "FLIK1"}])
        mon.on_capture_report(REPORT)
        (n,) = channel.sent
        assert n.route == "general"
        assert n.severity == "info"
        assert "FLIK1" in n.title
        assert "42" in n.title  # sample_count
        assert "21m" in n.title  # 1260s human-formatted
        assert "2026-07-14T11:00:00+00:00" in n.body
        assert "2026-07-14T12:00:00+00:00" in n.body

    def test_device_not_on_roster_is_silent(self):
        mon, _, channel = _monitoring(roster=[{"device_id": "FLIK2"}])
        mon.on_capture_report(REPORT)  # REPORT is for FLIK1
        assert channel.sent == []

    def test_missing_device_id_is_silent(self):
        mon, _, channel = _monitoring(roster=[{"device_id": "FLIK1"}])
        mon.on_capture_report({**REPORT, "device_id": ""})
        assert channel.sent == []


class RecordingMonitor:
    def __init__(self):
        self.reports = []

    def on_capture_report(self, record):
        self.reports.append(record)


class TestProcessCaptureObject:
    def _write(self, root: Path, key: str, payload: dict) -> None:
        target = root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")

    def test_report_parsed_and_delivered_to_monitor(self, tmp_path):
        key = "v1/FLIK1/captures/20260714_120000.json"
        self._write(tmp_path, key, REPORT)
        monitor = RecordingMonitor()
        summary = trigger_handler.process_capture_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            key,
            monitor=monitor,
        )
        assert summary == {"capture_reports": 1}
        (report,) = monitor.reports
        assert report["device_id"] == "FLIK1"
        assert report["total_duration_seconds"] == 1260.0

    def test_malformed_json_returns_zero(self, tmp_path):
        key = "v1/FLIK1/captures/20260714_120000.json"
        target = tmp_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{not json", encoding="utf-8")
        summary = trigger_handler.process_capture_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            key,
            monitor=RecordingMonitor(),
        )
        assert summary == {"capture_reports": 0}

    def test_monitor_failure_does_not_fail_processing(self, tmp_path):
        class Exploding:
            def on_capture_report(self, record):
                raise RuntimeError("boom")

        key = "v1/FLIK1/captures/20260714_120000.json"
        self._write(tmp_path, key, REPORT)
        summary = trigger_handler.process_capture_object(
            trigger_handler.LocalStorageAdapter(tmp_path),
            trigger_handler.CollectingWriter(),
            "bucket",
            key,
            monitor=Exploding(),
        )
        assert summary == {"capture_reports": 1}

    def test_processing_kind_recognizes_captures(self):
        assert trigger_handler._processing_kind("v1/FLIK1/captures/20260714_120000.json") == trigger_handler.ProcessingKind.CAPTURE

    def test_processing_kind_does_not_misclassify_other_keys(self):
        assert trigger_handler._processing_kind("v1/FLIK1/heartbeats/x.json") != trigger_handler.ProcessingKind.CAPTURE
        assert trigger_handler._processing_kind("v1/FLIK1/captures/nested/x.json") != trigger_handler.ProcessingKind.CAPTURE
