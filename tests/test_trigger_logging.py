from __future__ import annotations

import json
import logging
import os
import sys
from io import BytesIO
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from PIL import Image


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


def _event(*keys: str, etag: str | None = None, version_id: str | None = None) -> dict[str, object]:
    def s3_object(key: str) -> dict[str, str]:
        payload = {"key": key}
        if etag is not None:
            payload["eTag"] = etag
        if version_id is not None:
            payload["versionId"] = version_id
        return payload

    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "bucket-1"},
                    "object": s3_object(key),
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

    def read_text(
        self,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        etag: str | None = None,
    ) -> str:
        return json.dumps(self.payload)

    def read_json(
        self,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        etag: str | None = None,
    ) -> dict[str, object]:
        return self.payload

    def exists(self, bucket: str, key: str) -> bool:
        return False

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> list[str]:
        return []


class MemoryStorage:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def read_text(
        self,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        etag: str | None = None,
    ) -> str:
        return self.objects[key].decode("utf-8")

    def read_json(
        self,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        etag: str | None = None,
    ) -> dict[str, object]:
        return json.loads(self.read_text(bucket, key, version_id=version_id, etag=etag))

    def read_bytes(self, bucket: str, key: str) -> bytes:
        return self.objects[key]

    def write_bytes(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = body

    def exists(self, bucket: str, key: str) -> bool:
        return key in self.objects

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix) and key.endswith(suffix))


class MemoryProcessedObjectStore:
    def __init__(self) -> None:
        self.processing: set[str] = set()
        self.processed: set[str] = set()
        self.begin_count = 0

    def begin(
        self,
        event: trigger_handler.S3ObjectEvent,
        kind: trigger_handler.ProcessingKind,
    ) -> trigger_handler.IdempotencyClaim:
        self.begin_count += 1
        object_id = event.object_id
        if object_id is None:
            return trigger_handler.IdempotencyClaim(trigger_handler.IdempotencyDecision.UNAVAILABLE)
        if object_id in self.processed:
            return trigger_handler.IdempotencyClaim(trigger_handler.IdempotencyDecision.SKIP_DUPLICATE)
        if object_id in self.processing:
            return trigger_handler.IdempotencyClaim(trigger_handler.IdempotencyDecision.IN_FLIGHT)
        self.processing.add(object_id)
        return trigger_handler.IdempotencyClaim(trigger_handler.IdempotencyDecision.PROCESS, "attempt-1")

    def complete(self, event: trigger_handler.S3ObjectEvent, claim: trigger_handler.IdempotencyClaim) -> None:
        object_id = event.object_id
        if object_id is not None:
            self.processing.discard(object_id)
            self.processed.add(object_id)

    def fail(self, event: trigger_handler.S3ObjectEvent, claim: trigger_handler.IdempotencyClaim) -> None:
        object_id = event.object_id
        if object_id is not None:
            self.processing.discard(object_id)


def _conditional_failed() -> ClientError:
    return ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")


class FakeProcessedObjectsTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def put_item(self, Item: dict[str, object], **kwargs: object) -> None:
        object_id = str(Item["object_id"])
        existing = self.items.get(object_id)
        now = int(kwargs["ExpressionAttributeValues"][":now"])  # type: ignore[index]
        if existing and not (
            existing.get("status") == trigger_handler.ProcessedObjectStatus.PROCESSING.value
            and int(existing.get("lease_until", 0)) < now
        ):
            raise _conditional_failed()
        self.items[object_id] = dict(Item)

    def get_item(self, Key: dict[str, str], **kwargs: object) -> dict[str, object]:
        item = self.items.get(Key["object_id"])
        return {"Item": item} if item else {}

    def update_item(self, Key: dict[str, str], **kwargs: object) -> None:
        item = self.items[Key["object_id"]]
        values = kwargs["ExpressionAttributeValues"]  # type: ignore[index]
        if not (
            item.get("status") == values[":processing"]
            and item.get("attempt_id") == values[":attempt_id"]
        ):
            raise _conditional_failed()
        item["status"] = values[":processed"]
        item["ttl"] = values[":ttl"]
        item["updated_at"] = values[":now"]
        item.pop("lease_until", None)
        item.pop("attempt_id", None)

    def delete_item(self, Key: dict[str, str], **kwargs: object) -> None:
        item = self.items.get(Key["object_id"])
        if item is None:
            return
        values = kwargs["ExpressionAttributeValues"]  # type: ignore[index]
        if not (
            item.get("status") == values[":processing"]
            and item.get("attempt_id") == values[":attempt_id"]
        ):
            raise _conditional_failed()
        del self.items[Key["object_id"]]


def _store_with_fake_table(table: FakeProcessedObjectsTable) -> trigger_handler.ProcessedObjectStore:
    store = trigger_handler.ProcessedObjectStore(table_name="")
    store.table = table
    return store


def _s3_object_event(etag: str = "etag-1") -> trigger_handler.S3ObjectEvent:
    return trigger_handler.S3ObjectEvent(
        bucket="bucket-1",
        key="v1/device-1/results.json",
        etag=etag,
        version_id=None,
    )


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (10, 10), "white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def no_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger_handler, "S3StorageAdapter", trigger_handler.StorageAdapter)
    monkeypatch.setattr(trigger_handler, "DynamoWriter", lambda: object())
    monkeypatch.setattr(trigger_handler.activity, "record_s3_received", lambda *args, **kwargs: None)
    monkeypatch.setattr(trigger_handler.activity, "record_s3_processed", lambda *args, **kwargs: None)
    monkeypatch.setattr(trigger_handler.activity, "record_object_ignored", lambda *args, **kwargs: None)
    monkeypatch.setattr(trigger_handler.activity, "record_results_malformed", lambda *args, **kwargs: None)
    monkeypatch.setattr(trigger_handler.activity, "record_track_validation_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(trigger_handler.activity, "record_classification_validation_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(trigger_handler.activity, "record_composite_generation_failed", lambda *args, **kwargs: None)


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


def test_parse_s3_event_keeps_object_identity_and_decodes_key() -> None:
    records = trigger_handler.parse_s3_event(
        _event("v1/device+1/results.json", etag="etag-1", version_id="version-1")
    )

    assert records == [
        trigger_handler.S3ObjectEvent(
            bucket="bucket-1",
            key="v1/device 1/results.json",
            etag="etag-1",
            version_id="version-1",
        )
    ]


def test_processed_object_store_skips_processed_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100)
    table = FakeProcessedObjectsTable()
    store = _store_with_fake_table(table)
    event = _s3_object_event()

    claim = store.begin(event, trigger_handler.ProcessingKind.RESULTS)
    store.complete(event, claim)

    assert store.begin(event, trigger_handler.ProcessingKind.RESULTS).decision == (
        trigger_handler.IdempotencyDecision.SKIP_DUPLICATE
    )


def test_processed_object_store_blocks_in_flight_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100)
    table = FakeProcessedObjectsTable()
    store = _store_with_fake_table(table)
    event = _s3_object_event()

    assert store.begin(event, trigger_handler.ProcessingKind.RESULTS).decision == trigger_handler.IdempotencyDecision.PROCESS
    assert store.begin(event, trigger_handler.ProcessingKind.RESULTS).decision == trigger_handler.IdempotencyDecision.IN_FLIGHT


def test_processed_object_store_reclaims_stale_processing(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeProcessedObjectsTable()
    store = _store_with_fake_table(table)
    event = _s3_object_event()

    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100)
    first = store.begin(event, trigger_handler.ProcessingKind.RESULTS)
    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100 + trigger_handler.PROCESSED_OBJECT_LEASE_SECONDS + 1)
    second = store.begin(event, trigger_handler.ProcessingKind.RESULTS)

    assert first.decision == trigger_handler.IdempotencyDecision.PROCESS
    assert second.decision == trigger_handler.IdempotencyDecision.PROCESS
    assert second.attempt_id != first.attempt_id


def test_processed_object_store_owner_token_protects_processed_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100)
    table = FakeProcessedObjectsTable()
    store = _store_with_fake_table(table)
    event = _s3_object_event()

    claim = store.begin(event, trigger_handler.ProcessingKind.RESULTS)
    store.complete(event, claim)
    store.fail(event, claim)

    assert table.items[event.object_id]["status"] == trigger_handler.ProcessedObjectStatus.PROCESSED.value


def test_processed_object_store_stale_attempt_cannot_finish_reclaimed_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeProcessedObjectsTable()
    store = _store_with_fake_table(table)
    event = _s3_object_event()

    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100)
    stale_claim = store.begin(event, trigger_handler.ProcessingKind.RESULTS)
    monkeypatch.setattr(trigger_handler, "_epoch_seconds", lambda: 100 + trigger_handler.PROCESSED_OBJECT_LEASE_SECONDS + 1)
    current_claim = store.begin(event, trigger_handler.ProcessingKind.RESULTS)

    with pytest.raises(ClientError):
        store.complete(event, stale_claim)
    store.fail(event, stale_claim)
    store.complete(event, current_claim)

    assert table.items[event.object_id]["status"] == trigger_handler.ProcessedObjectStatus.PROCESSED.value


def test_lambda_handler_skips_duplicate_object(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryProcessedObjectStore()
    calls = 0

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", process)
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    response = trigger_handler.lambda_handler(
        _event("v1/device-1/results.json", "v1/device-1/results.json", etag="etag-1"),
        None,
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == [{"tracks": 1}, {"skipped_duplicate": 1}]
    assert calls == 1
    assert any(payload["action"] == "duplicate" for payload in _payloads(caplog))


def test_lambda_handler_processes_changed_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryProcessedObjectStore()
    calls = 0

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", process)

    trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)
    trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-2"), None)

    assert calls == 2


def test_lambda_handler_missing_identity_processes_normally(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryProcessedObjectStore()
    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", lambda *args, **kwargs: {"tracks": 1})
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    response = trigger_handler.lambda_handler(_event("v1/device-1/results.json"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == [{"tracks": 1}]
    assert any(payload["action"] == "idempotency_unavailable" for payload in _payloads(caplog))


def test_lambda_handler_ignored_object_does_not_claim_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryProcessedObjectStore()
    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)

    response = trigger_handler.lambda_handler(_event("v1/device-1/composites/image.jpg", etag="etag-1"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == []
    assert store.begin_count == 0


def test_lambda_handler_in_flight_duplicate_does_not_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryProcessedObjectStore()
    event = trigger_handler.S3ObjectEvent("bucket-1", "v1/device-1/results.json", "etag-1", None)
    store.begin(event, trigger_handler.ProcessingKind.RESULTS)
    calls = 0

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", process)

    with pytest.raises(RuntimeError, match="already processing"):
        trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)

    assert calls == 0


def test_lambda_handler_failure_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryProcessedObjectStore()
    calls = 0

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", process)

    with pytest.raises(RuntimeError):
        trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)
    response = trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == [{"tracks": 1}]
    assert calls == 2


def test_s3_read_failure_does_not_complete_idempotency() -> None:
    class FailingStorage(MemoryStorage):
        def read_json(
            self,
            bucket: str,
            key: str,
            *,
            version_id: str | None = None,
            etag: str | None = None,
        ) -> dict[str, object]:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    store = MemoryProcessedObjectStore()
    event = trigger_handler.S3ObjectEvent("bucket-1", "v1/device-1/results.json", "etag-1", None)

    with pytest.raises(ClientError):
        trigger_handler.process_s3_object(
            FailingStorage({}),
            trigger_handler.CollectingWriter(),
            event,
            store,
        )

    assert event.object_id not in store.processing
    assert event.object_id not in store.processed


def test_lambda_handler_failure_cleanup_error_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailCleanupStore(MemoryProcessedObjectStore):
        def fail(self, event: trigger_handler.S3ObjectEvent, claim: trigger_handler.IdempotencyClaim) -> None:
            raise RuntimeError("cleanup failed")

    store = FailCleanupStore()
    calls = 0

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", process)
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)

    assert calls == 1
    assert any(
        payload["action"] == "idempotency_error" and payload["error"] == "cleanup failed"
        for payload in _payloads(caplog)
    )


def test_lambda_handler_complete_failure_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class CompleteFailsStore(MemoryProcessedObjectStore):
        def complete(self, event: trigger_handler.S3ObjectEvent, claim: trigger_handler.IdempotencyClaim) -> None:
            raise RuntimeError("complete failed")

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", CompleteFailsStore)
    monkeypatch.setattr(trigger_handler, "process_results_object", lambda *args, **kwargs: {"tracks": 1})
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    with pytest.raises(RuntimeError, match="complete failed"):
        trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)

    assert any(
        payload["action"] == "idempotency_error" and payload["error"] == "complete failed"
        for payload in _payloads(caplog)
    )


def test_lambda_handler_begin_failure_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = trigger_handler.ProcessedObjectStore(table_name="")
    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, "process_results_object", lambda *args, **kwargs: {"tracks": 1})
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    with pytest.raises(RuntimeError, match="PROCESSED_OBJECTS_TABLE is required"):
        trigger_handler.lambda_handler(_event("v1/device-1/results.json", etag="etag-1"), None)

    assert any(
        payload["action"] == "idempotency_error"
        and payload["error"] == "PROCESSED_OBJECTS_TABLE is required"
        for payload in _payloads(caplog)
    )


def test_lambda_handler_received_activity_failure_releases_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryProcessedObjectStore()
    event = _event("v1/device-1/results.json", etag="etag-1")
    calls = 0

    def fail_received(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("activity failed")

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler.activity, "record_s3_received", fail_received)
    monkeypatch.setattr(trigger_handler, "process_results_object", lambda *args, **kwargs: {"tracks": 1})

    with pytest.raises(RuntimeError, match="activity failed"):
        trigger_handler.lambda_handler(event, None)
    response = trigger_handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == [{"tracks": 1}]


def test_lambda_handler_processed_activity_failure_releases_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryProcessedObjectStore()
    event = _event("v1/device-1/results.json", etag="etag-1")
    activity_calls = 0
    process_calls = 0

    def fail_processed(*args: object, **kwargs: object) -> None:
        nonlocal activity_calls
        activity_calls += 1
        if activity_calls == 1:
            raise RuntimeError("processed activity failed")

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal process_calls
        process_calls += 1
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler.activity, "record_s3_processed", fail_processed)
    monkeypatch.setattr(trigger_handler, "process_results_object", process)

    with pytest.raises(RuntimeError, match="processed activity failed"):
        trigger_handler.lambda_handler(event, None)
    response = trigger_handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == [{"tracks": 1}]
    assert process_calls == 2


def test_process_s3_object_passes_object_identity_to_processor(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryProcessedObjectStore()
    event = trigger_handler.S3ObjectEvent(
        bucket="bucket-1",
        key="v1/device-1/results.json",
        etag="etag-1",
        version_id="version-1",
    )
    captured: dict[str, object] = {}

    def process(
        storage: object,
        writer: object,
        bucket: str,
        key: str,
        *,
        version_id: str | None = None,
        etag: str | None = None,
    ) -> dict[str, int]:
        captured.update({"version_id": version_id, "etag": etag})
        return {"tracks": 1}

    monkeypatch.setattr(trigger_handler, "process_results_object", process)

    trigger_handler.process_s3_object(
        MemoryStorage({}),
        trigger_handler.CollectingWriter(),
        event,
        store,
    )

    assert captured == {"version_id": "version-1", "etag": "etag-1"}


def test_heartbeat_malformed_json_read_returns_zero_rows() -> None:
    class MalformedJsonStorage(MemoryStorage):
        def read_json(
            self,
            bucket: str,
            key: str,
            *,
            version_id: str | None = None,
            etag: str | None = None,
        ) -> dict[str, object]:
            raise ValueError("bad json")

    summary = trigger_handler.process_heartbeat_object(
        MalformedJsonStorage({}),
        trigger_handler.CollectingWriter(),
        "bucket-1",
        "v1/device-1/heartbeats/heartbeat.json",
    )

    assert summary == {"heartbeats": 0}


def test_heartbeat_passes_through_pipeline_upload_network_and_incoming_fields() -> None:
    """The device (bugcam run) ships network_interfaces/pipeline/upload/incoming
    sections beyond the original cpu_temp/storage/dot_status fields. Without a
    declared field, Pydantic's default extra="ignore" drops them silently at
    Heartbeat(**payload) -- no error, nothing in the stored record -- which is
    exactly what let this go unnoticed against a real device for a while."""
    payload = {
        "device_id": "flik5",
        "timestamp": "2026-07-23T10:00:00Z",
        "cpu_temperature_celsius": 42.0,
        "storage_free_bytes": 123,
        "storage_total_bytes": 456,
        "uptime_seconds": 100.0,
        "dot_status": [{"dot_id": "dot01", "last_modified": None}],
        "network_interfaces": [{"interface": "wlan0", "rx_bytes": 111, "tx_bytes": 222}],
        "incoming": {"flick_videos": 2, "flick_video_bytes": 8, "dot_dirs": 0, "ready_dot_tracks": 0},
        "pipeline": {
            "workers": {"Detection": True, "Classification": True},
            "video_queue": 2923,
            "classification_queue": 0,
            "detection": {"count": 4, "avg_seconds": 41.2, "max_seconds": 60.0},
        },
        "upload": {"pending": 7, "bytes_uploaded_total": 999},
    }
    storage = MemoryStorage({"v1/flik5/heartbeats/heartbeat.json": json.dumps(payload).encode("utf-8")})
    writer = trigger_handler.CollectingWriter()

    summary = trigger_handler.process_heartbeat_object(
        storage, writer, "bucket-1", "v1/flik5/heartbeats/heartbeat.json"
    )

    assert summary == {"heartbeats": 1}
    (stored,) = writer.heartbeats
    assert stored["network_interfaces"] == payload["network_interfaces"]
    assert stored["incoming"] == payload["incoming"]
    assert stored["pipeline"]["video_queue"] == 2923
    assert float(stored["pipeline"]["detection"]["avg_seconds"]) == pytest.approx(41.2)
    assert stored["upload"] == payload["upload"]


def test_heartbeat_without_new_fields_still_processes_cleanly() -> None:
    """Older device firmware that only ever sent cpu_temp/storage/dot_status
    must keep working unchanged -- the new fields are optional."""
    payload = {
        "device_id": "flik4",
        "timestamp": "2026-07-23T10:00:00Z",
        "cpu_temperature_celsius": 40.0,
        "storage_free_bytes": 1,
        "storage_total_bytes": 2,
    }
    storage = MemoryStorage({"v1/flik4/heartbeats/heartbeat.json": json.dumps(payload).encode("utf-8")})
    writer = trigger_handler.CollectingWriter()

    summary = trigger_handler.process_heartbeat_object(
        storage, writer, "bucket-1", "v1/flik4/heartbeats/heartbeat.json"
    )

    assert summary == {"heartbeats": 1}
    (stored,) = writer.heartbeats
    assert stored["network_interfaces"] is None
    assert stored["pipeline"] is None
    assert stored["upload"] is None
    assert stored["incoming"] is None


def test_environment_malformed_json_read_returns_zero_rows() -> None:
    class MalformedJsonStorage(MemoryStorage):
        def read_json(
            self,
            bucket: str,
            key: str,
            *,
            version_id: str | None = None,
            etag: str | None = None,
        ) -> dict[str, object]:
            raise ValueError("bad json")

    summary = trigger_handler.process_environment_object(
        MalformedJsonStorage({}),
        trigger_handler.CollectingWriter(),
        "bucket-1",
        "v1/device-1/environment/reading.json",
    )

    assert summary == {"environmental_readings": 0}


@pytest.mark.parametrize(
    ("key", "process_name", "summary"),
    [
        ("v1/device-1/heartbeats/heartbeat.json", "process_heartbeat_object", {"heartbeats": 1}),
        ("v1/device-1/environment/reading.json", "process_environment_object", {"environmental_readings": 1}),
    ],
)
def test_lambda_handler_skips_duplicate_heartbeat_and_environment(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    process_name: str,
    summary: dict[str, int],
) -> None:
    store = MemoryProcessedObjectStore()
    calls = 0

    def process(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return summary

    monkeypatch.setattr(trigger_handler, "ProcessedObjectStore", lambda: store)
    monkeypatch.setattr(trigger_handler, process_name, process)

    response = trigger_handler.lambda_handler(_event(key, key, etag="etag-1"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["processed"] == [summary, {"skipped_duplicate": 1}]
    assert calls == 1


@pytest.mark.parametrize(
    "event",
    [
        trigger_handler.S3ObjectEvent("bucket-1", "v1/device-1/heartbeats/heartbeat.json", "etag-1", None),
        trigger_handler.S3ObjectEvent("bucket-1", "v1/device-1/environment/reading.json", "etag-1", None),
    ],
)
def test_heartbeat_environment_s3_read_failure_does_not_complete_idempotency(
    event: trigger_handler.S3ObjectEvent,
) -> None:
    class FailingStorage(MemoryStorage):
        def read_json(
            self,
            bucket: str,
            key: str,
            *,
            version_id: str | None = None,
            etag: str | None = None,
        ) -> dict[str, object]:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    store = MemoryProcessedObjectStore()

    with pytest.raises(ClientError):
        trigger_handler.process_s3_object(
            FailingStorage({}),
            trigger_handler.CollectingWriter(),
            event,
            store,
        )

    assert event.object_id not in store.processing
    assert event.object_id not in store.processed


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


def test_results_processing_creates_missing_dot_composite_before_track_write() -> None:
    results_key = "v1/FLIK2-dot01/20260412/results.json"
    composite_key = "v1/FLIK2-dot01/20260412/composites/12224_163315.jpg"
    storage = MemoryStorage(
        {
            results_key: json.dumps(
                {
                    "source_device": "FLIK2-dot01",
                    "date": "20260412",
                    "tracks": [
                        {
                            "track_id": "12224",
                            "timestamp": "163315",
                            "final_prediction": {
                                "family": "Family",
                                "genus": "Genus",
                                "species": "Species",
                                "family_confidence": 0.9,
                                "genus_confidence": 0.8,
                                "species_confidence": 0.7,
                            },
                            "num_detections": 1,
                            "frames": [],
                        }
                    ],
                }
            ).encode("utf-8"),
            "v1/FLIK2-dot01/20260412/labels/12224.json": json.dumps(
                {
                    "resolution": {"width": 100, "height": 80},
                    "points": [{"x": 10, "y": 20, "width": 10, "height": 10, "frameIndex": 1505}],
                }
            ).encode("utf-8"),
            "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000000.jpg": _jpeg_bytes(),
        }
    )
    writer = trigger_handler.CollectingWriter()

    summary = trigger_handler.process_results_object(storage, writer, "bucket", results_key)

    assert summary["tracks"] == 1
    assert summary["composites_created"] == 1
    assert storage.exists("bucket", composite_key)
    assert writer.tracks[0]["composite_key"] == composite_key


def test_composite_generation_failure_does_not_skip_track(caplog: pytest.LogCaptureFixture) -> None:
    results_key = "v1/FLIK2-dot01/20260412/results.json"
    storage = MemoryStorage(
        {
            results_key: json.dumps(
                {
                    "source_device": "FLIK2-dot01",
                    "date": "20260412",
                    "tracks": [
                        {
                            "track_id": "12224",
                            "timestamp": "163315",
                            "final_prediction": {
                                "family": "Family",
                                "genus": "Genus",
                                "species": "Species",
                                "family_confidence": 0.9,
                                "genus_confidence": 0.8,
                                "species_confidence": 0.7,
                            },
                            "num_detections": 1,
                            "frames": [],
                        }
                    ],
                }
            ).encode("utf-8"),
            "v1/FLIK2-dot01/20260412/labels/12224.json": json.dumps(
                {
                    "resolution": {"width": 100, "height": 80},
                    "points": [{"x": 10, "y": 20, "width": 10, "height": 10, "frameIndex": 1505}],
                }
            ).encode("utf-8"),
            "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000000.jpg": b"not-a-jpeg",
        }
    )
    writer = trigger_handler.CollectingWriter()
    caplog.set_level(logging.INFO, logger=trigger_handler.logger.name)

    summary = trigger_handler.process_results_object(storage, writer, "bucket", results_key)

    payloads = _payloads(caplog)
    assert summary["tracks"] == 1
    assert summary["composites_failed"] == 1
    assert len(writer.tracks) == 1
    assert any(
        payload["kind"] == "composite"
        and payload["reason"] == "generation_failed"
        and payload["track_id"] == "12224"
        for payload in payloads
    )
