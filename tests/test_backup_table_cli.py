from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.path.insert(0, str(TRIGGER_SRC))

import backup_table_cli  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))


class _FakeTable:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self._pages = [items[:2], items[2:]] if len(items) > 2 else [items]

    def scan(self, **kwargs):
        page_index = 0 if "ExclusiveStartKey" not in kwargs else 1
        page = self._pages[page_index] if page_index < len(self._pages) else []
        response = {"Items": page}
        if page_index == 0 and len(self._pages) > 1:
            response["LastEvaluatedKey"] = {"object_id": "cursor"}
        return response


class _FakeDynamoResource:
    def __init__(self, table: _FakeTable) -> None:
        self._table = table

    def Table(self, name: str) -> _FakeTable:
        return self._table


class _FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)


def test_backup_table_paginates_scan_and_writes_one_gzip_ndjson_object(monkeypatch):
    items = [
        {"object_id": "a", "bucket": "b1"},
        {"object_id": "b", "bucket": "b2"},
        {"object_id": "c", "bucket": "b3"},
    ]
    fake_table = _FakeTable(items)
    fake_s3 = _FakeS3Client()

    monkeypatch.setattr(backup_table_cli.boto3, "resource", lambda name: _FakeDynamoResource(fake_table))
    monkeypatch.setattr(backup_table_cli.boto3, "client", lambda name: fake_s3)

    result = backup_table_cli.backup_table("sensing-garden-detections", "scl-sensing-garden", "backups/dynamodb")

    assert result["item_count"] == 3
    assert result["bucket"] == "scl-sensing-garden"
    assert result["key"].startswith("backups/dynamodb/sensing-garden-detections/")
    assert result["key"].endswith(".jsonl.gz")

    assert len(fake_s3.put_calls) == 1
    call = fake_s3.put_calls[0]
    assert call["Bucket"] == "scl-sensing-garden"
    assert call["Key"] == result["key"]

    decompressed = gzip.decompress(call["Body"]).decode("utf-8")
    lines = [json.loads(line) for line in decompressed.splitlines()]
    assert lines == items


def test_backup_table_dry_run_scans_but_does_not_write(monkeypatch):
    fake_table = _FakeTable([{"object_id": "a"}])
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(backup_table_cli.boto3, "resource", lambda name: _FakeDynamoResource(fake_table))
    monkeypatch.setattr(backup_table_cli.boto3, "client", lambda name: fake_s3)

    result = backup_table_cli.backup_table("sensing-garden-detections", "scl-sensing-garden", "backups/dynamodb", dry_run=True)

    assert result["item_count"] == 1
    assert result["dry_run"] is True
    assert fake_s3.put_calls == []


def test_main_rejects_prefix_inside_watched_v1_or_v2():
    with pytest.raises(SystemExit):
        backup_table_cli.main(["--table", "x", "--bucket", "y", "--prefix", "v1/backups"])
    with pytest.raises(SystemExit):
        backup_table_cli.main(["--table", "x", "--bucket", "y", "--prefix", "v2/backups"])


def test_json_default_preserves_int_vs_float_decimals():
    assert backup_table_cli._json_default(backup_table_cli.Decimal("5")) == 5
    assert isinstance(backup_table_cli._json_default(backup_table_cli.Decimal("5")), int)
    assert backup_table_cli._json_default(backup_table_cli.Decimal("5.5")) == 5.5
    assert isinstance(backup_table_cli._json_default(backup_table_cli.Decimal("5.5")), float)
