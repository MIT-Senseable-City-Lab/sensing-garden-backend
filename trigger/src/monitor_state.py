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
from typing import Any, Dict, List, Optional, Tuple

import boto3

MONITOR_STATE_TABLE = os.environ.get("MONITOR_STATE_TABLE", "sensing-garden-monitor-state")

# Bandwidth trend checks look back bandwidth_trend_window_hours (default 2h) by
# elapsed time, anchored to each sample's own timestamp -- at the real ~5min
# heartbeat interval, the old cap of 8 held well under an hour of history,
# so a multi-hour window could never have enough data to evaluate. Generous
# headroom here (60 samples ~= 5h at 5min intervals) covers the default window
# with room to spare if it's later widened.
MAX_SAMPLES = 60


class DeviceState:
    def __init__(self, device_id: str, checks: Optional[Dict[str, Dict[str, Any]]] = None,
                 samples: Optional[List[Dict[str, float]]] = None,
                 bandwidth: Optional[Dict[str, Any]] = None) -> None:
        self.device_id = device_id
        self.checks: Dict[str, Dict[str, Any]] = checks or {}
        self.samples: List[Dict[str, float]] = samples or []
        self.bandwidth: Dict[str, Any] = bandwidth or {}

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

    # -- cumulative bandwidth (daily/monthly, unbounded by the sample window) --
    def record_bandwidth_delta(self, counter: float, now: datetime) -> Tuple[float, float]:
        """Rolls a device-reported monotonic lifetime byte counter into running
        daily/monthly totals. A counter that doesn't increase (first observation,
        or a drop from a device reboot resetting its counter) contributes no
        delta -- we can't attribute it to usage, so it just rebases silently;
        check_restart already pages on the reboot itself via uptime_seconds."""
        last_counter = self.bandwidth.get("last_counter")
        delta = counter - last_counter if last_counter is not None and counter >= last_counter else 0.0
        today = now.date().isoformat()
        month = now.strftime("%Y-%m")
        daily_bytes = self.bandwidth.get("daily_bytes", 0.0) if self.bandwidth.get("daily_date") == today else 0.0
        monthly_bytes = self.bandwidth.get("monthly_bytes", 0.0) if self.bandwidth.get("monthly_month") == month else 0.0
        daily_bytes += delta
        monthly_bytes += delta
        self.bandwidth = {
            "last_counter": counter,
            "daily_date": today,
            "daily_bytes": daily_bytes,
            "monthly_month": month,
            "monthly_bytes": monthly_bytes,
        }
        return daily_bytes, monthly_bytes


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
        return DeviceState(
            device_id, checks=payload.get("checks"), samples=payload.get("samples"), bandwidth=payload.get("bandwidth")
        )

    def put(self, state: DeviceState, now: datetime) -> None:
        self.table.put_item(
            Item={
                "device_id": state.device_id,
                "state_json": json.dumps(
                    {"checks": state.checks, "samples": state.samples, "bandwidth": state.bandwidth}
                ),
                "updated_at": now.isoformat(),
            }
        )
