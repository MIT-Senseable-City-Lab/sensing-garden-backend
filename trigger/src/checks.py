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
    "uptime_seconds",
    "pending_bytes",
    "pending",
    "avg_bytes_per_sec",
    "results_total",
    "results_finalized_unpublished",
    "videos_captured_total",
    "videos_uploaded_total",
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
    # uptime_seconds comes from the pipeline process's own monotonic clock
    # (heartbeat["pipeline"]["uptime_seconds"]), not the top-level field the
    # device also sends -- that one is host /proc/uptime, which keeps
    # climbing straight through a bugcam service restart and so can never
    # detect one. check_restart needs the process-lifetime value.
    pipeline = heartbeat.get("pipeline")
    if isinstance(pipeline, dict):
        value = _number(pipeline.get("uptime_seconds"))
        if value is not None:
            samples["uptime_seconds"] = value
    upload = heartbeat.get("upload")
    if isinstance(upload, dict):
        for src, dst in (
            ("pending_bytes", "pending_bytes"),
            ("pending", "pending"),
        ):
            value = _number(upload.get(src))
            if value is not None:
                samples[dst] = value
        # Device reports throughput as decimal Mbytes/sec (pollen.py:
        # nbytes / 1e6 / seconds); convert to bytes/sec to compare against
        # upload_min_bytes_per_sec.
        avg_mbps = _number(upload.get("avg_mbps"))
        if avg_mbps is not None:
            samples["avg_bytes_per_sec"] = avg_mbps * 1_000_000
    results = heartbeat.get("results")
    if isinstance(results, dict):
        for src, dst in (
            ("total", "results_total"),
            ("finalized_unpublished", "results_finalized_unpublished"),
        ):
            value = _number(results.get(src))
            if value is not None:
                samples[dst] = value
    videos = heartbeat.get("videos")
    if isinstance(videos, dict):
        for src, dst in (
            ("captured_total", "videos_captured_total"),
            ("uploaded_total", "videos_uploaded_total"),
        ):
            value = _number(videos.get(src))
            if value is not None:
                samples[dst] = value
    return samples


def _series(history: Sequence[Dict[str, float]], field: str) -> List[float]:
    return [entry[field] for entry in history if field in entry]


def _series_within_window(
    history: Sequence[Dict[str, float]], field: str, now: datetime, window_hours: float
) -> List[float]:
    """Like _series, but only samples from the last window_hours -- anchored to
    each sample's own timestamp, not position in the list. A trend over "the
    last N samples" silently means different things as heartbeat frequency
    changes; this always means the same elapsed time."""
    cutoff = now.timestamp() - window_hours * 3600
    return [entry[field] for entry in history if field in entry and entry.get("ts", 0) >= cutoff]


def _strictly_increasing(values: Sequence[float]) -> bool:
    return len(values) >= 2 and all(b > a for a, b in zip(values, values[1:]))


def _human_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


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
    # Absolute-bytes floor only -- the fractional threshold lives in
    # check_disk_trend (WARNING tier) so the two checks don't both fire off
    # the same underlying condition at different severities.
    floor_breached = free < cfg.disk_min_free_bytes
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
    """Early heads-up at the last disk_min_free_fraction of free space -- WARNING
    tier, distinct from check_disk_space's absolute-bytes CRITICAL floor.

    Previously projected days-to-full from the free-bytes slope over just the
    first/last history points; a brief capture burst could swing that linear
    estimate enough to false-trigger at 80% free, and re-estimating it fresh
    every sweep made the finding flap between BAD/OK, notifying repeatedly.
    A plain fraction-of-total threshold only flips when free space actually
    crosses the line."""
    free = _number(heartbeat.get("storage_free_bytes"))
    total = _number(heartbeat.get("storage_total_bytes"))
    if free is None or not total:
        return []
    fraction_free = free / total
    if fraction_free <= cfg.disk_min_free_fraction:
        return [
            Finding(
                device_id,
                "disk_trend",
                BAD,
                WARNING,
                f"{device_id}: disk trending full",
                f"{_human_bytes(free)} free of {_human_bytes(total)} ({fraction_free:.0%})",
            )
        ]
    return [Finding(device_id, "disk_trend", OK, WARNING, f"{device_id}: disk trend OK", f"{fraction_free:.0%} free")]


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
    """Upload health: three trends over the last bandwidth_trend_window_hours
    (default 2h) of history, by elapsed time -- not just "the last N
    samples," which silently means a different span whenever heartbeat
    frequency changes, and not a single instantaneous reading either: a
    momentarily noisy queue depth crossing the threshold on one heartbeat
    must not flap BAD/OK (observed live: one device flipped 15+ times in a
    few hours before this fix).

    Field names match what the device actually sends (pollen.py's Pollen.stats()):
    `pending` (live queue count) and `avg_mbps` (decimal MB/s, converted to
    bytes/sec in extract_samples) -- not the older `queue_depth`/
    `last_flush_bytes_per_sec` names the device has never sent."""
    upload = heartbeat.get("upload")
    if not isinstance(upload, dict):
        return []
    problems: List[str] = []
    depth = _number(upload.get("pending"))
    window_hours = cfg.bandwidth_trend_window_hours
    depth_window = _series_within_window(history, "pending", now, window_hours)
    if len(depth_window) >= cfg.upload_queue_depth_min_samples and all(
        d > cfg.upload_queue_depth_max for d in depth_window
    ):
        problems.append(
            f"queue depth over {cfg.upload_queue_depth_max} for the last {window_hours:.0f}h "
            f"(currently {int(depth_window[-1])})"
        )
    pending_window = _series_within_window(history, "pending_bytes", now, window_hours)
    if len(pending_window) >= cfg.pending_bytes_growth_samples and _strictly_increasing(pending_window):
        problems.append(f"pending bytes growing over the last {window_hours:.0f}h ({_human_bytes(pending_window[-1])} queued)")
    speed_window = _series_within_window(history, "avg_bytes_per_sec", now, window_hours)
    if len(speed_window) >= cfg.upload_slow_consecutive_samples and all(
        s < cfg.upload_min_bytes_per_sec for s in speed_window
    ):
        problems.append(
            f"upload speed under {_human_bytes(cfg.upload_min_bytes_per_sec)}/s for the last {window_hours:.0f}h "
            f"({_human_bytes(speed_window[-1])}/s)"
        )
    if problems:
        return [Finding(device_id, "bandwidth", BAD, WARNING, f"{device_id}: upload struggling", "; ".join(problems))]
    if depth is None and "pending_bytes" not in upload and "avg_mbps" not in upload:
        return []
    return [Finding(device_id, "bandwidth", OK, WARNING, f"{device_id}: uploads OK", "queue draining normally")]


def check_restart(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    """Detects a process restart from process-lifetime uptime: the device derives
    it from a monotonic clock within the running process (a systemd restart after
    a crash is otherwise invisible -- host uptime keeps climbing), so it only ever
    grows across one process's life. A drop between consecutive heartbeats means
    the pipeline restarted -- but only if the new value is actually small
    (restart_min_uptime_seconds): a genuine reboot resets uptime near zero, so a
    drop that lands anywhere else (e.g. "10.8d" to "10.8d") is measurement noise,
    not a restart. An ordinary OK/BAD check (not a one-shot event) so a
    crash-looping device re-fires the transition -- and therefore re-notifies --
    on every restart, not just the first."""
    uptimes = _series(history, "uptime_seconds")
    if len(uptimes) < 2:
        return []
    previous, current = uptimes[-2], uptimes[-1]
    if current < previous and current < cfg.restart_min_uptime_seconds:
        return [
            Finding(
                device_id,
                "restart",
                BAD,
                WARNING,
                f"{device_id}: restarted",
                f"Process uptime dropped from {_human_duration(previous)} to {_human_duration(current)}",
            )
        ]
    return [Finding(device_id, "restart", OK, WARNING, f"{device_id}: uptime nominal", f"up {_human_duration(current)}")]


def check_video_backlog(
    device_id: str,
    heartbeat: Dict[str, Any],
    history: Sequence[Dict[str, float]],
    now: datetime,
    cfg: MonitorConfig,
) -> List[Finding]:
    """Videos captured on-device but not yet uploaded/cleared -- distinct from
    check_bandwidth's generic upload queue, this is video-specific so a false-
    trigger storm or a stuck uploader shows up even if other artifact types are
    draining fine. Dormant until devices send videos.captured_total/uploaded_total."""
    captured = _series(history, "videos_captured_total")
    uploaded = _series(history, "videos_uploaded_total")
    if not captured or not uploaded:
        return []
    backlog = [c - u for c, u in zip(captured, uploaded)]
    current = backlog[-1]
    window = backlog[-cfg.video_backlog_growth_samples:]
    growing = len(window) >= cfg.video_backlog_growth_samples and _strictly_increasing(window)
    over_max = current > cfg.video_backlog_max
    if growing or over_max:
        parts = []
        if over_max:
            parts.append(f"{int(current)} video(s) pending (max {cfg.video_backlog_max})")
        if growing:
            parts.append(f"backlog growing ({int(current)} now)")
        return [Finding(device_id, "video_backlog", BAD, WARNING, f"{device_id}: video backlog", "; ".join(parts))]
    return [Finding(device_id, "video_backlog", OK, WARNING, f"{device_id}: videos OK", f"{int(current)} pending upload")]


CONTENT_CHECKS = (
    check_disk_space,
    check_disk_trend,
    check_thermal,
    check_dot_freshness,
    check_results_backlog,
    check_bandwidth,
    check_restart,
    check_video_backlog,
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
