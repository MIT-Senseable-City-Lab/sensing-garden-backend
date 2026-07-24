"""Thresholds and wiring for fleet monitoring, sourced from the environment.

Every knob the checks use lives here so tuning is a Lambda env change, never a
device rollout (SPEC-fleet-monitoring-and-notifications, item 6).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class MonitorConfig:
    # liveness: newest heartbeat older than this many seconds -> device down.
    # Default 3x the device's default heartbeat_upload_interval (300 s).
    liveness_max_age_seconds: float = 900.0
    # disk: free space floor, absolute and fractional
    disk_min_free_bytes: float = 5 * 1024**3
    disk_min_free_fraction: float = 0.10
    disk_time_to_full_days: float = 7.0
    # thermal: sustained CPU temperature ceiling (consecutive samples)
    thermal_max_celsius: float = 80.0
    thermal_consecutive_samples: int = 2
    # DOT freshness: a DOT this stale while its FLIK is alive means camera death
    dot_max_age_seconds: float = 1800.0
    # bandwidth / results (dormant until heartbeat v2 fields arrive)
    upload_queue_depth_max: int = 50
    upload_min_bytes_per_sec: float = 100 * 1024
    upload_slow_consecutive_samples: int = 3
    results_unpublished_consecutive_samples: int = 3
    results_growth_samples: int = 6
    pending_bytes_growth_samples: int = 6
    # video backlog: captured-but-not-yet-uploaded videos piling up on the device
    # (dormant until devices send the videos.captured_total/uploaded_total fields)
    video_backlog_max: int = 20
    video_backlog_growth_samples: int = 6
    # cumulative bandwidth: rolling daily/monthly totals against a cell data cap
    # (dormant until devices send upload.bytes_uploaded_total; 0 = cap disabled)
    bandwidth_daily_cap_bytes: float = 0.0
    bandwidth_monthly_cap_bytes: float = 0.0
    # re-page cadence for criticals that stay bad
    critical_repage_seconds: float = 6 * 3600.0
    # re-page cadence for warnings that stay bad (longer than critical -- a
    # reminder, not a page)
    warning_repage_seconds: float = 24 * 3600.0
    # one log-error digest page per device per window
    log_error_cooldown_seconds: float = 6 * 3600.0
    # periodic per-device stats report: new-track count over the trailing window
    digest_window_hours: float = 8.0
    # channels / backstop
    ntfy_emergency_url: str = ""
    ntfy_general_url: str = ""
    slack_emergency_url: str = ""
    slack_general_url: str = ""
    healthchecks_ping_url: str = ""

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        return cls(
            liveness_max_age_seconds=_env_float("MONITOR_LIVENESS_MAX_AGE_SECONDS", cls.liveness_max_age_seconds),
            disk_min_free_bytes=_env_float("MONITOR_DISK_MIN_FREE_BYTES", cls.disk_min_free_bytes),
            disk_min_free_fraction=_env_float("MONITOR_DISK_MIN_FREE_FRACTION", cls.disk_min_free_fraction),
            disk_time_to_full_days=_env_float("MONITOR_DISK_TIME_TO_FULL_DAYS", cls.disk_time_to_full_days),
            thermal_max_celsius=_env_float("MONITOR_THERMAL_MAX_CELSIUS", cls.thermal_max_celsius),
            thermal_consecutive_samples=int(_env_float("MONITOR_THERMAL_CONSECUTIVE_SAMPLES", cls.thermal_consecutive_samples)),
            dot_max_age_seconds=_env_float("MONITOR_DOT_MAX_AGE_SECONDS", cls.dot_max_age_seconds),
            upload_queue_depth_max=int(_env_float("MONITOR_UPLOAD_QUEUE_DEPTH_MAX", cls.upload_queue_depth_max)),
            upload_min_bytes_per_sec=_env_float("MONITOR_UPLOAD_MIN_BYTES_PER_SEC", cls.upload_min_bytes_per_sec),
            upload_slow_consecutive_samples=int(
                _env_float("MONITOR_UPLOAD_SLOW_CONSECUTIVE_SAMPLES", cls.upload_slow_consecutive_samples)
            ),
            results_unpublished_consecutive_samples=int(
                _env_float("MONITOR_RESULTS_UNPUBLISHED_CONSECUTIVE_SAMPLES", cls.results_unpublished_consecutive_samples)
            ),
            results_growth_samples=int(_env_float("MONITOR_RESULTS_GROWTH_SAMPLES", cls.results_growth_samples)),
            pending_bytes_growth_samples=int(
                _env_float("MONITOR_PENDING_BYTES_GROWTH_SAMPLES", cls.pending_bytes_growth_samples)
            ),
            video_backlog_max=int(_env_float("MONITOR_VIDEO_BACKLOG_MAX", cls.video_backlog_max)),
            video_backlog_growth_samples=int(
                _env_float("MONITOR_VIDEO_BACKLOG_GROWTH_SAMPLES", cls.video_backlog_growth_samples)
            ),
            bandwidth_daily_cap_bytes=_env_float("MONITOR_BANDWIDTH_DAILY_CAP_BYTES", cls.bandwidth_daily_cap_bytes),
            bandwidth_monthly_cap_bytes=_env_float(
                "MONITOR_BANDWIDTH_MONTHLY_CAP_BYTES", cls.bandwidth_monthly_cap_bytes
            ),
            critical_repage_seconds=_env_float("MONITOR_CRITICAL_REPAGE_SECONDS", cls.critical_repage_seconds),
            warning_repage_seconds=_env_float("MONITOR_WARNING_REPAGE_SECONDS", cls.warning_repage_seconds),
            log_error_cooldown_seconds=_env_float("MONITOR_LOG_ERROR_COOLDOWN_SECONDS", cls.log_error_cooldown_seconds),
            digest_window_hours=_env_float("MONITOR_DIGEST_WINDOW_HOURS", cls.digest_window_hours),
            ntfy_emergency_url=os.environ.get("MONITOR_NTFY_EMERGENCY_URL", ""),
            ntfy_general_url=os.environ.get("MONITOR_NTFY_GENERAL_URL", ""),
            slack_emergency_url=os.environ.get("MONITOR_SLACK_EMERGENCY_URL", ""),
            slack_general_url=os.environ.get("MONITOR_SLACK_GENERAL_URL", ""),
            healthchecks_ping_url=os.environ.get("MONITOR_HEALTHCHECKS_PING_URL", ""),
        )
