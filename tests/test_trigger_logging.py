from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.path.insert(0, str(TRIGGER_SRC))

import trigger_handler  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)


def _event(*keys: str) -> dict[str, object]:
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "bucket-1"},
                    "object": {"key": key},
                }
            }
            for key in keys
        ]
    }


def _payloads(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [json.loads(record.getMessage()) for record in caplog.records if record.name == trigger_handler.logger.name]


class JsonStorage:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read_text(self, bucket: str, key: str) -> str:
        return json.dumps(self.payload)

    def read_json(self, bucket: str, key: str) -> dict[str, object]:
        return self.payload

    def exists(self, bucket: str, key: str) -> bool:
        return False

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> list[str]:
        return []


@pytest.fixture(autouse=True)
def no_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger_handler, "S3StorageAdapter", lambda: object())
    monkeypatch.setattr(trigger_handler, "DynamoWriter", lambda: object())
    monkeypatch.setattr(trigger_handler.activity, "record_s3_processed", lambda *args, **kwargs: None)


def test_lambda_handler_logs_received_records_and_ignored_v1_keys(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary = {"tracks": 2, "classifications": 3, "devices": 1, "videos": 1}
    monkeypatch.setattr(trigger_handler, "process_results_object", lambda *args, **kwargs: summary)
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    response = trigger_handler.lambda_handler(
        _event("v1/device-1/results.json", "v1/device-1/notes.txt"),
        None,
    )

    payloads = _payloads(caplog)
    assert response["statusCode"] == 200
    assert any(payload["action"] == "received" and payload["key"] == "v1/device-1/results.json" for payload in payloads)
    assert any(payload["action"] == "received" and payload["key"] == "v1/device-1/notes.txt" for payload in payloads)
    assert any(
        payload["action"] == "ignored"
        and payload["key"] == "v1/device-1/notes.txt"
        and payload["reason"] == "unsupported_key"
        for payload in payloads
    )


def test_lambda_handler_logs_successful_results_processing_summary(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary = {"tracks": 4, "classifications": 6, "devices": 1, "videos": 1}
    monkeypatch.setattr(trigger_handler, "process_results_object", lambda *args, **kwargs: summary)
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    response = trigger_handler.lambda_handler(_event("v1/device-1/results.json"), None)

    payloads = _payloads(caplog)
    assert response["statusCode"] == 200
    assert any(
        payload["action"] == "processed"
        and payload["key"] == "v1/device-1/results.json"
        and payload["status"] == "success"
        and payload["summary"] == summary
        for payload in payloads
    )


def test_lambda_handler_logs_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom(*args: object, **kwargs: object) -> dict[str, int]:
        raise RuntimeError("boom")

    monkeypatch.setattr(trigger_handler, "process_results_object", boom)
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    with pytest.raises(RuntimeError):
        trigger_handler.lambda_handler(_event("v1/device-1/results.json"), None)

    payloads = _payloads(caplog)
    assert any(
        payload["action"] == "failed"
        and payload["key"] == "v1/device-1/results.json"
        and payload["error"] == "boom"
        for payload in payloads
    )


def test_dot_date_results_use_timestamped_track_ids() -> None:
    storage = JsonStorage(
        {
            "source_device": "FLIK2-dot01",
            "date": "20260412",
            "tracks": [
                {
                    "track_id": "3409",
                    "timestamp": "163112",
                    "final_prediction": {
                        "family": "Family_1",
                        "genus": "Genus_1",
                        "species": "Species_1",
                        "family_confidence": 0.9,
                        "genus_confidence": 0.8,
                        "species_confidence": 0.7,
                    },
                    "num_detections": 1,
                    "frames": [],
                },
                {
                    "track_id": "3409",
                    "timestamp": "163116",
                    "final_prediction": {
                        "family": "Family_2",
                        "genus": "Genus_2",
                        "species": "Species_2",
                        "family_confidence": 0.9,
                        "genus_confidence": 0.8,
                        "species_confidence": 0.7,
                    },
                    "num_detections": 1,
                    "frames": [],
                },
            ],
        }
    )
    writer = trigger_handler.CollectingWriter()

    summary = trigger_handler.process_results_object(
        storage,
        writer,
        "bucket",
        "v1/FLIK2-dot01/20260412/results.json",
    )

    assert summary["tracks"] == 2
    assert [item["track_id"] for item in writer.tracks] == ["3409_163112", "3409_163116"]
