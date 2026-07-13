"""Per-device monitoring state, one DynamoDB item per device.

Per-device items (not one fleet blob) because trigger invocations run
concurrently: two heartbeats arriving together must not race a shared
read-modify-write. The check/sample payload is stored as a single JSON string
attribute — state is opaque to DynamoDB, and floats never meet Decimal.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3

MONITOR_STATE_TABLE = os.environ.get("MONITOR_STATE_TABLE", "sensing-garden-monitor-state")

MAX_SAMPLES = 8


class DeviceState:
    def __init__(self, device_id: str, checks: Optional[Dict[str, Dict[str, Any]]] = None,
                 samples: Optional[List[Dict[str, float]]] = None) -> None:
        self.device_id = device_id
        self.checks: Dict[str, Dict[str, Any]] = checks or {}
        self.samples: List[Dict[str, float]] = samples or []

    # -- check status ------------------------------------------------------
    def status(self, check: str) -> Optional[str]:
        entry = self.checks.get(check)
        return entry.get("status") if entry else None

    def since(self, check: str) -> Optional[str]:
        entry = self.checks.get(check)
        return entry.get("since") if entry else None

    def transition(self, check: str, status: str, now: datetime) -> None:
        self.checks[check] = {"status": status, "since": now.isoformat(), "last_notified_at": None}

    def last_notified(self, check: str) -> Optional[datetime]:
        entry = self.checks.get(check)
        raw = entry.get("last_notified_at") if entry else None
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def mark_notified(self, check: str, now: datetime) -> None:
        self.checks.setdefault(check, {"status": None, "since": now.isoformat()})["last_notified_at"] = now.isoformat()

    # -- sample history ----------------------------------------------------
    def record_sample(self, sample: Dict[str, float]) -> None:
        if sample:
            self.samples.append(sample)
            self.samples = self.samples[-MAX_SAMPLES:]


class MonitorStateStore:
    """Thin persistence for DeviceState. Table resource injectable for tests."""

    def __init__(self, table: Any = None) -> None:
        self._table = table

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = boto3.resource("dynamodb").Table(MONITOR_STATE_TABLE)
        return self._table

    def get(self, device_id: str) -> DeviceState:
        response = self.table.get_item(Key={"device_id": device_id})
        item = response.get("Item")
        if not item:
            return DeviceState(device_id)
        try:
            payload = json.loads(item.get("state_json", "{}"))
        except (TypeError, ValueError):
            payload = {}
        return DeviceState(device_id, checks=payload.get("checks"), samples=payload.get("samples"))

    def put(self, state: DeviceState, now: datetime) -> None:
        self.table.put_item(
            Item={
                "device_id": state.device_id,
                "state_json": json.dumps({"checks": state.checks, "samples": state.samples}),
                "updated_at": now.isoformat(),
            }
        )
