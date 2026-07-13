"""Pure fleet-health checks over heartbeat payloads.

No AWS, no IO: every function here decides from plain data — the fresh heartbeat
row, a bounded sample history, the clock, and thresholds — and returns Findings.
Content checks run at heartbeat ingest; liveness runs from the scheduled sweep
(absence is not an event). Checks whose fields are missing return nothing, so
heartbeat-v2 checks ship dormant and wake when devices start sending the fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from monitor_config import MonitorConfig

OK = "OK"
BAD = "BAD"

CRITICAL = "critical"
WARNING = "warning"

# Fields sampled from each heartbeat into state history (oldest -> newest).
SAMPLE_FIELDS = (
    "storage_free_bytes",
    "cpu_temperature_celsius",
    "pending_bytes",
    "queue_depth",
    "last_flush_bytes_per_sec",
    "results_total",
    "results_finalized_unpublished",
)


@dataclass(frozen=True)
class Finding:
    device_id: str
    check: str
    status: str  # OK | BAD
    severity: str  # critical | warning
    title: str
    body: str


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_samples(heartbeat: Dict[str, Any]) -> Dict[str, float]:
    """Flatten the numeric fields we keep history for. Missing fields are absent,
    never zero — a device that doesn't report a field must not look healthy at 0."""
    samples: Dict[str, float] = {}
    ts = parse_timestamp(heartbeat.get("timestamp"))
    if ts is not None:
        samples["ts"] = ts.timestamp()
    for field in ("storage_free_bytes", "cpu_temperature_celsius"):
        value = _number(heartbeat.get(field))
        if value is not None:
            samples[field] = value
    upload = heartbeat.get("upload")
    if isinstance(upload, dict):
        for src, dst in (
            ("pending_bytes", "pending_bytes"),
            ("queue_depth", "queue_depth"),
            ("last_flush_bytes_per_sec", "last_flush_bytes_per_sec"),
        ):
            value = _number(upload.get(src))
            if value is not None:
                samples[dst] = value
    results = heartbeat.get("results")
    if isinstance(results, dict):
        for src, dst in (
            ("total", "results_total"),
            ("finalized_unpublished", "results_finalized_unpublished"),
        ):
            value = _number(results.get(src))
            if value is not None:
                samples[dst] = value
    return samples


def _series(history: Sequence[Dict[str, float]], field: str) -> List[float]:
    return [entry[field] for entry in history if field in entry]


def _strictly_increasing(values: Sequence[float]) -> bool:
    return len(values) >= 2 and all(b > a for a, b in zip(values, values[1:]))


def _human_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


# ---------------------------------------------------------------------------
# Content checks: (device_id, heartbeat, history, now, cfg) -> list[Finding].
# History includes the current heartbeat's samples as its newest entry.
# ---------------------------------------------------------------------------

def check_disk_space(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    free = _number(heartbeat.get("storage_free_bytes"))
    total = _number(heartbeat.get("storage_total_bytes"))
    if free is None:
        return []
    floor_breached = free < cfg.disk_min_free_bytes or (
        total is not None and total > 0 and free / total < cfg.disk_min_free_fraction
    )
    if floor_breached:
        detail = f"{_human_bytes(free)} free"
        if total:
            detail += f" of {_human_bytes(total)} ({free / total:.0%})"
        return [Finding(device_id, "disk_space", BAD, CRITICAL, f"{device_id}: disk low", detail)]
    return [Finding(device_id, "disk_space", OK, CRITICAL, f"{device_id}: disk OK", f"{_human_bytes(free)} free")]


def check_disk_trend(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    """Time-to-full projection from the free-bytes slope over state history.
    Separate check key from the floor (which is critical): a full disk in a week
    is a warning you act on, not a page."""
    points = [(entry["ts"], entry["storage_free_bytes"]) for entry in history
              if "ts" in entry and "storage_free_bytes" in entry]
    if len(points) < 4:
        return []
    (t0, free0), (t1, free1) = points[0], points[-1]
    elapsed = t1 - t0
    if elapsed <= 0:
        return []
    drain_per_second = (free0 - free1) / elapsed
    if drain_per_second <= 0:
        return [Finding(device_id, "disk_trend", OK, WARNING, f"{device_id}: disk trend OK", "free space not shrinking")]
    days_to_full = free1 / drain_per_second / 86400
    if days_to_full < cfg.disk_time_to_full_days:
        return [
            Finding(
                device_id,
                "disk_trend",
                BAD,
                WARNING,
                f"{device_id}: disk trending full",
                f"~{days_to_full:.1f} days to full at current rate ({_human_bytes(free1)} free)",
            )
        ]
    return [Finding(device_id, "disk_trend", OK, WARNING, f"{device_id}: disk trend OK", f"~{days_to_full:.0f} days headroom")]


def check_thermal(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    temps = _series(history, "cpu_temperature_celsius")
    if not temps:
        return []
    window = temps[-cfg.thermal_consecutive_samples:]
    if len(window) >= cfg.thermal_consecutive_samples and all(t > cfg.thermal_max_celsius for t in window):
        return [
            Finding(
                device_id,
                "thermal",
                BAD,
                WARNING,
                f"{device_id}: CPU hot",
                f"{window[-1]:.1f} °C for {len(window)} consecutive heartbeats (limit {cfg.thermal_max_celsius:.0f} °C)",
            )
        ]
    if window and window[-1] <= cfg.thermal_max_celsius:
        return [Finding(device_id, "thermal", OK, WARNING, f"{device_id}: CPU temp OK", f"{window[-1]:.1f} °C")]
    return []  # single hot sample: not yet sustained, not yet recovered


def check_dot_freshness(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    dots = heartbeat.get("dot_status")
    if not isinstance(dots, list) or not dots:
        return []
    stale: List[str] = []
    for dot in dots:
        if not isinstance(dot, dict):
            continue
        dot_id = str(dot.get("dot_id", "?"))
        last_modified = parse_timestamp(dot.get("last_modified"))
        if last_modified is None:
            stale.append(f"{dot_id} (never seen)")
        elif (now - last_modified).total_seconds() > cfg.dot_max_age_seconds:
            age_min = (now - last_modified).total_seconds() / 60
            stale.append(f"{dot_id} ({age_min:.0f} min)")
    if stale:
        return [
            Finding(
                device_id,
                "dot_freshness",
                BAD,
                WARNING,
                f"{device_id}: DOT stale",
                "No recent frames from: " + ", ".join(stale) + " — FLIK itself is alive",
            )
        ]
    return [Finding(device_id, "dot_freshness", OK, WARNING, f"{device_id}: DOTs OK", f"{len(dots)} DOT(s) fresh")]


def check_results_backlog(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    unpublished = _series(history, "results_finalized_unpublished")
    totals = _series(history, "results_total")
    if not unpublished and not totals:
        return []
    window = unpublished[-cfg.results_unpublished_consecutive_samples:]
    stuck = (
        len(window) >= cfg.results_unpublished_consecutive_samples and all(v > 0 for v in window)
    )
    growing = _strictly_increasing(totals[-cfg.results_growth_samples:]) and len(
        totals[-cfg.results_growth_samples:]
    ) >= cfg.results_growth_samples
    if stuck or growing:
        parts = []
        if stuck:
            parts.append(f"{int(window[-1])} finalized result dir(s) never published")
        if growing:
            parts.append(f"leftover result dirs growing ({int(totals[-1])} now)")
        return [
            Finding(device_id, "results_backlog", BAD, WARNING, f"{device_id}: results backlog", "; ".join(parts))
        ]
    return [
        Finding(
            device_id,
            "results_backlog",
            OK,
            WARNING,
            f"{device_id}: results OK",
            f"{int(totals[-1]) if totals else 0} leftover dir(s)",
        )
    ]


def check_bandwidth(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    upload = heartbeat.get("upload")
    if not isinstance(upload, dict):
        return []
    problems: List[str] = []
    depth = _number(upload.get("queue_depth"))
    if depth is not None and depth > cfg.upload_queue_depth_max:
        problems.append(f"queue depth {int(depth)} (max {cfg.upload_queue_depth_max})")
    pending = _series(history, "pending_bytes")
    window = pending[-cfg.pending_bytes_growth_samples:]
    if len(window) >= cfg.pending_bytes_growth_samples and _strictly_increasing(window):
        problems.append(f"pending bytes growing ({_human_bytes(window[-1])} queued)")
    speeds = _series(history, "last_flush_bytes_per_sec")
    speed_window = speeds[-cfg.upload_slow_consecutive_samples:]
    if len(speed_window) >= cfg.upload_slow_consecutive_samples and all(
        s < cfg.upload_min_bytes_per_sec for s in speed_window
    ):
        problems.append(
            f"upload speed {_human_bytes(speed_window[-1])}/s (floor {_human_bytes(cfg.upload_min_bytes_per_sec)}/s)"
        )
    if problems:
        return [Finding(device_id, "bandwidth", BAD, WARNING, f"{device_id}: upload struggling", "; ".join(problems))]
    if depth is None and not pending and not speeds:
        return []
    return [Finding(device_id, "bandwidth", OK, WARNING, f"{device_id}: uploads OK", "queue draining normally")]


CONTENT_CHECKS = (
    check_disk_space,
    check_disk_trend,
    check_thermal,
    check_dot_freshness,
    check_results_backlog,
    check_bandwidth,
)


def run_content_checks(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    findings: List[Finding] = []
    for check in CONTENT_CHECKS:
        findings.extend(check(device_id, heartbeat, history, now, cfg))
    return findings


# ---------------------------------------------------------------------------
# Liveness: sweep-side, over the roster and each device's latest heartbeat.
# ---------------------------------------------------------------------------

def check_liveness(
    roster: Iterable[Dict[str, Any]],
    latest_heartbeats: Dict[str, Dict[str, Any]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    findings: List[Finding] = []
    for device in roster:
        device_id = str(device.get("device_id", ""))
        if not device_id:
            continue
        heartbeat = latest_heartbeats.get(device_id)
        seen = parse_timestamp(heartbeat.get("timestamp")) if heartbeat else None
        if seen is None:
            findings.append(
                Finding(
                    device_id,
                    "liveness",
                    BAD,
                    CRITICAL,
                    f"{device_id}: never seen",
                    "Device is on the roster but has no heartbeat on record",
                )
            )
            continue
        age = (now - seen).total_seconds()
        if age > cfg.liveness_max_age_seconds:
            findings.append(
                Finding(
                    device_id,
                    "liveness",
                    BAD,
                    CRITICAL,
                    f"{device_id}: silent",
                    f"Last heartbeat {age / 60:.0f} min ago (limit {cfg.liveness_max_age_seconds / 60:.0f} min)",
                )
            )
        else:
            findings.append(
                Finding(
                    device_id,
                    "liveness",
                    OK,
                    CRITICAL,
                    f"{device_id}: back online",
                    f"Heartbeat {age / 60:.1f} min ago",
                )
            )
    return findings
