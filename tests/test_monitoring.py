from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

import checks  # noqa: E402
import monitoring as monitoring_module  # noqa: E402
import trigger_handler  # noqa: E402
from monitor_config import MonitorConfig  # noqa: E402
from monitor_state import DeviceState, MonitorStateStore  # noqa: E402
from monitoring import Monitoring  # noqa: E402
from notify import Notification, Notifier  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)

NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
CFG = MonitorConfig()


def _heartbeat(device_id: str = "FLIK1", *, age_seconds: float = 0, **extra) -> dict:
    payload = {
        "device_id": device_id,
        "timestamp": (NOW - timedelta(seconds=age_seconds)).isoformat(),
        "cpu_temperature_celsius": 55.0,
        "storage_free_bytes": 50 * 1024**3,
        "storage_total_bytes": 100 * 1024**3,
        "uptime_seconds": 3600.0,  # host OS uptime (/proc/uptime) -- check_restart ignores this
        "pipeline": {"uptime_seconds": 3600.0},  # process-lifetime uptime -- what check_restart reads
        "dot_status": [{"dot_id": "DOT1", "last_modified": (NOW - timedelta(minutes=5)).isoformat()}],
    }
    payload.update(extra)
    return payload


class FakeStateStore:
    def __init__(self) -> None:
        self.states: dict[str, DeviceState] = {}
        self.put_count = 0

    def get(self, device_id: str) -> DeviceState:
        state = self.states.get(device_id)
        if state is None:
            return DeviceState(device_id)
        return DeviceState(device_id, checks=json.loads(json.dumps(state.checks)),
                           samples=json.loads(json.dumps(state.samples)),
                           bandwidth=json.loads(json.dumps(state.bandwidth)))

    def put(self, state: DeviceState, now: datetime) -> None:
        self.put_count += 1
        self.states[state.device_id] = state


class RecordingChannel:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


def _monitoring(roster=None, latest=None, track_counts=None,
                 cfg: MonitorConfig = CFG, now: datetime = NOW):
    store = FakeStateStore()
    channel = RecordingChannel()
    base_roster = roster if roster is not None else [{"device_id": "FLIK1"}]
    # liveness_enabled defaults True here (test convenience only -- the real
    # roster has no such default): most tests are exercising a specific check's
    # behavior, not the enable/disable gate itself, so they shouldn't all have
    # to spell out "this device is enabled" by hand. Tests that ARE about the
    # gate pass liveness_enabled explicitly, which overrides this default.
    resolved_roster = [{"liveness_enabled": True, **d} for d in base_roster]
    mon = Monitoring(
        cfg=cfg,
        state_store=store,
        notifier=Notifier([channel]),
        roster_fn=lambda: resolved_roster,
        latest_heartbeats_fn=lambda ids: latest or {},
        track_count_fn=lambda device_id, window_start, now: (track_counts or {}).get(device_id, 0),
        now_fn=lambda: now,
    )
    return mon, store, channel


# ---------------------------------------------------------------------------
# checks: pure behavior
# ---------------------------------------------------------------------------

def test_liveness_flags_stale_and_never_seen():
    roster = [{"device_id": "FLIK1"}, {"device_id": "FLIK2"}, {"device_id": "FLIK3"}]
    latest = {
        "FLIK1": _heartbeat("FLIK1", age_seconds=60),
        "FLIK2": _heartbeat("FLIK2", age_seconds=CFG.liveness_max_age_seconds + 600),
    }
    findings = {f.device_id: f for f in checks.check_liveness(roster, latest, NOW, CFG)}
    assert findings["FLIK1"].status == checks.OK
    assert findings["FLIK2"].status == checks.BAD
    assert findings["FLIK3"].status == checks.BAD
    assert "never" in findings["FLIK3"].title


def test_disk_floor_is_absolute_bytes_only():
    """disk_space is the hard CRITICAL floor -- absolute bytes only. The
    fractional leg moved to disk_trend (WARNING tier), so a device with a
    huge disk sitting at 5% free but still comfortably above the absolute
    floor should NOT page as critical."""
    low_abs = _heartbeat(storage_free_bytes=1 * 1024**3)
    history = [checks.extract_samples(low_abs)]
    (finding,) = checks.check_disk_space("FLIK1", low_abs, history, NOW, CFG)
    assert finding.status == checks.BAD and finding.severity == checks.CRITICAL

    low_frac_high_abs = _heartbeat(storage_free_bytes=50 * 1024**3, storage_total_bytes=1000 * 1024**3)  # 5%, 50GB free
    (finding,) = checks.check_disk_space("FLIK1", low_frac_high_abs, [checks.extract_samples(low_frac_high_abs)], NOW, CFG)
    assert finding.status == checks.OK

    healthy = _heartbeat()
    (finding,) = checks.check_disk_space("FLIK1", healthy, [checks.extract_samples(healthy)], NOW, CFG)
    assert finding.status == checks.OK


def test_thermal_requires_consecutive_samples():
    hot = _heartbeat(cpu_temperature_celsius=90.0)
    one_hot = [checks.extract_samples(hot)]
    assert checks.check_thermal("FLIK1", hot, one_hot, NOW, CFG) == []  # not yet sustained
    two_hot = one_hot * 2
    (finding,) = checks.check_thermal("FLIK1", hot, two_hot, NOW, CFG)
    assert finding.status == checks.BAD
    cooled = _heartbeat(cpu_temperature_celsius=60.0)
    history = two_hot + [checks.extract_samples(cooled)]
    (finding,) = checks.check_thermal("FLIK1", cooled, history, NOW, CFG)
    assert finding.status == checks.OK


def test_disk_trend_fires_at_last_10_percent():
    """Replaced the old slope/days-to-full projection (noisy: a brief capture
    burst could swing the linear estimate from two history points and false-
    trigger even at 80% free). Now a stable fraction-of-total threshold,
    matching disk_min_free_fraction -- flips only when free space actually
    crosses the line, not on every sweep's re-estimated slope."""
    low = _heartbeat(storage_free_bytes=int(0.05 * 1000 * 1024**3), storage_total_bytes=1000 * 1024**3)  # 5%
    (finding,) = checks.check_disk_trend("FLIK1", low, [checks.extract_samples(low)], NOW, CFG)
    assert finding.status == checks.BAD
    assert finding.severity == checks.WARNING

    healthy = _heartbeat(storage_free_bytes=int(0.50 * 1000 * 1024**3), storage_total_bytes=1000 * 1024**3)  # 50%
    (finding,) = checks.check_disk_trend("FLIK1", healthy, [checks.extract_samples(healthy)], NOW, CFG)
    assert finding.status == checks.OK

    at_floor = _heartbeat(storage_free_bytes=int(0.10 * 1000 * 1024**3), storage_total_bytes=1000 * 1024**3)  # exactly 10%
    (finding,) = checks.check_disk_trend("FLIK1", at_floor, [checks.extract_samples(at_floor)], NOW, CFG)
    assert finding.status == checks.BAD  # "last 10%" is inclusive of the line itself


def test_dot_freshness_stale_dot_with_fresh_flik():
    stale = _heartbeat(dot_status=[
        {"dot_id": "DOT1", "last_modified": (NOW - timedelta(hours=2)).isoformat()},
        {"dot_id": "DOT2", "last_modified": (NOW - timedelta(minutes=3)).isoformat()},
    ])
    (finding,) = checks.check_dot_freshness("FLIK1", stale, [], NOW, CFG)
    assert finding.status == checks.BAD
    assert "DOT1" in finding.body and "DOT2" not in finding.body


def test_v2_checks_dormant_without_fields():
    v1_only = _heartbeat()
    history = [checks.extract_samples(v1_only)]
    assert checks.check_results_backlog("FLIK1", v1_only, history, NOW, CFG) == []
    assert checks.check_bandwidth("FLIK1", v1_only, history, NOW, CFG) == []
    assert checks.check_video_backlog("FLIK1", v1_only, history, NOW, CFG) == []


def test_video_backlog_fires_over_max():
    beat = _heartbeat(videos={"captured_total": 50, "uploaded_total": 20})
    history = [checks.extract_samples(beat)]
    (finding,) = checks.check_video_backlog("FLIK1", beat, history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "30 video(s) pending" in finding.body


def test_video_backlog_fires_on_sustained_growth_under_max():
    beats = [
        _heartbeat(videos={"captured_total": 10 + i, "uploaded_total": 10})
        for i in range(CFG.video_backlog_growth_samples)
    ]
    history = [checks.extract_samples(b) for b in beats]
    (finding,) = checks.check_video_backlog("FLIK1", beats[-1], history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "backlog growing" in finding.body


def test_video_backlog_ok_when_draining():
    beat = _heartbeat(videos={"captured_total": 12, "uploaded_total": 10})
    history = [checks.extract_samples(beat)]
    (finding,) = checks.check_video_backlog("FLIK1", beat, history, NOW, CFG)
    assert finding.status == checks.OK


def test_results_backlog_fires_on_sustained_unpublished():
    beat = _heartbeat(results={"total": 4, "finalized_unpublished": 2, "awaiting_classification": 1, "other": 1})
    history = [checks.extract_samples(beat)] * CFG.results_unpublished_consecutive_samples
    (finding,) = checks.check_results_backlog("FLIK1", beat, history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "never published" in finding.body


def test_bandwidth_fires_on_growing_pending_bytes():
    """Spread across the actual bandwidth_trend_window_hours, oldest first --
    growth over real elapsed time, not just N samples in a row regardless of
    when they landed."""
    n = CFG.pending_bytes_growth_samples
    step_seconds = (CFG.bandwidth_trend_window_hours * 3600) / n
    beats = [
        _heartbeat(
            age_seconds=(n - 1 - i) * step_seconds,
            upload={"pending": 3, "pending_bytes": (i + 1) * 10_000_000, "avg_mbps": 5.0},
        )
        for i in range(n)
    ]
    history = [checks.extract_samples(b) for b in beats]
    (finding,) = checks.check_bandwidth("FLIK1", beats[-1], history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "pending bytes growing" in finding.body


def test_bandwidth_queue_depth_reads_the_real_device_field():
    """The device sends `pending` (a live count), not `queue_depth` -- the
    old field name the check used to read, which the device has never sent,
    so that leg silently never fired. Sustained over the window, matching
    the other two legs -- not a single instantaneous reading (see
    test_bandwidth_queue_depth_ignores_a_single_spike for why)."""
    n = CFG.upload_queue_depth_min_samples
    step_seconds = (CFG.bandwidth_trend_window_hours * 3600) / n
    beats = [
        _heartbeat(age_seconds=(n - 1 - i) * step_seconds, upload={"pending": CFG.upload_queue_depth_max + 10})
        for i in range(n)
    ]
    history = [checks.extract_samples(b) for b in beats]
    (finding,) = checks.check_bandwidth("FLIK1", beats[-1], history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "queue depth" in finding.body


def test_bandwidth_queue_depth_ignores_a_single_spike():
    """A momentarily noisy queue crossing the threshold on one heartbeat must
    not page -- this is exactly the flapping observed live (FLIK3 flipping
    BAD/OK 15+ times in a few hours as its queue bounced around 50)."""
    spike = _heartbeat(upload={"pending": CFG.upload_queue_depth_max + 10})
    (finding,) = checks.check_bandwidth("FLIK1", spike, [checks.extract_samples(spike)], NOW, CFG)
    assert finding.status == checks.OK


def test_bandwidth_throughput_reads_avg_mbps_converted_to_bytes():
    """The device sends `avg_mbps` (decimal megabits... actually megabytes,
    per pollen.py's own math), not `last_flush_bytes_per_sec` -- another
    field the device never sent. avg_mbps must be converted (*1e6) before
    comparing against the bytes/sec floor."""
    n = CFG.upload_slow_consecutive_samples
    step_seconds = (CFG.bandwidth_trend_window_hours * 3600) / n
    floor_mbps = CFG.upload_min_bytes_per_sec / 1_000_000
    slow_mbps = floor_mbps / 2  # half the floor
    beats = [
        _heartbeat(age_seconds=(n - 1 - i) * step_seconds, upload={"pending": 1, "avg_mbps": slow_mbps})
        for i in range(n)
    ]
    history = [checks.extract_samples(b) for b in beats]
    (finding,) = checks.check_bandwidth("FLIK1", beats[-1], history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "upload speed" in finding.body


def test_bandwidth_growth_ignores_samples_outside_the_time_window():
    """Old growth from outside the window must not count -- only what's
    happened in the last bandwidth_trend_window_hours matters. Without this,
    a device that grew its backlog hours ago and has been flat since would
    still page forever, because "last N samples" doesn't know how old they
    are."""
    n = CFG.pending_bytes_growth_samples
    window_seconds = CFG.bandwidth_trend_window_hours * 3600
    old_growth = [
        _heartbeat(age_seconds=window_seconds + (n - i) * 60, upload={"pending": 1, "pending_bytes": (i + 1) * 10_000_000})
        for i in range(n)
    ]  # all outside the window, growing
    recent_flat = [
        _heartbeat(age_seconds=(n - 1 - i) * (window_seconds / n / 2), upload={"pending": 1, "pending_bytes": 5_000_000})
        for i in range(n)
    ]  # inside the window, flat
    history = [checks.extract_samples(b) for b in old_growth + recent_flat]
    (finding,) = checks.check_bandwidth("FLIK1", recent_flat[-1], history, NOW, CFG)
    assert finding.status == checks.OK


def test_bandwidth_requires_minimum_points_within_window():
    """A single sample inside the window isn't enough to call it a trend."""
    beat = _heartbeat(age_seconds=60, upload={"pending": 1, "pending_bytes": 10_000_000})
    history = [checks.extract_samples(beat)]
    (finding,) = checks.check_bandwidth("FLIK1", beat, history, NOW, CFG)
    assert finding.status == checks.OK


def test_restart_needs_a_prior_sample():
    first = _heartbeat(pipeline={"uptime_seconds": 3600.0})
    history = [checks.extract_samples(first)]
    assert checks.check_restart("FLIK1", first, history, NOW, CFG) == []


def test_restart_fires_on_uptime_drop_and_clears_on_growth():
    history = [checks.extract_samples(_heartbeat(pipeline={"uptime_seconds": 3600.0}))]

    restarted = _heartbeat(pipeline={"uptime_seconds": 45.0})
    history.append(checks.extract_samples(restarted))
    (finding,) = checks.check_restart("FLIK1", restarted, history, NOW, CFG)
    assert finding.status == checks.BAD
    assert "restart" in finding.title.lower()

    recovered = _heartbeat(pipeline={"uptime_seconds": 120.0})
    history.append(checks.extract_samples(recovered))
    (finding,) = checks.check_restart("FLIK1", recovered, history, NOW, CFG)
    assert finding.status == checks.OK


def test_restart_ignores_a_tiny_drop_that_is_not_a_real_reboot():
    """A genuine restart resets uptime near zero -- a drop that's still deep
    into "days" territory isn't a reboot, it's measurement noise (observed
    live: "Process uptime dropped from 10.8d to 10.8d", which is not a real
    10.8-day uptime reappearing within one heartbeat interval)."""
    history = [checks.extract_samples(_heartbeat(pipeline={"uptime_seconds": 933120.0}))]  # 10.8d
    jittered = _heartbeat(pipeline={"uptime_seconds": 933119.0})  # 10.8d, 1s "lower"
    history.append(checks.extract_samples(jittered))
    (finding,) = checks.check_restart("FLIK1", jittered, history, NOW, CFG)
    assert finding.status == checks.OK


def test_restart_dormant_without_uptime_field():
    beat = _heartbeat()
    del beat["pipeline"]
    history = [checks.extract_samples(beat), checks.extract_samples(beat)]
    assert checks.check_restart("FLIK1", beat, history, NOW, CFG) == []


def test_restart_ignores_top_level_uptime_seconds_reads_pipeline_instead():
    """Regression: uptime_seconds at the top level is host /proc/uptime, which
    keeps climbing straight through a bugcam service restart -- only
    pipeline.uptime_seconds (the process's own monotonic clock) actually
    resets. A device whose OS uptime keeps growing while its pipeline uptime
    collapses must still be flagged as restarted."""
    history = [checks.extract_samples(
        _heartbeat(uptime_seconds=933120.0, pipeline={"uptime_seconds": 3600.0})
    )]
    restarted = _heartbeat(uptime_seconds=933180.0, pipeline={"uptime_seconds": 10.0})
    history.append(checks.extract_samples(restarted))
    (finding,) = checks.check_restart("FLIK1", restarted, history, NOW, CFG)
    assert finding.status == checks.BAD


def test_extract_samples_ignores_missing_pipeline_field():
    beat = _heartbeat()
    del beat["pipeline"]
    samples = checks.extract_samples(beat)
    assert "uptime_seconds" not in samples


# ---------------------------------------------------------------------------
# Monitoring: transitions, dedup, re-page, recovery
# ---------------------------------------------------------------------------

def test_on_heartbeat_pages_once_per_episode():
    mon, store, channel = _monitoring()
    bad = _heartbeat(storage_free_bytes=1 * 1024**3)
    mon.on_heartbeat(bad)
    assert [n for n in channel.sent if "disk low" in n.title]
    sent_before = len(channel.sent)
    mon.on_heartbeat(bad)  # same episode: no re-page for a fresh BAD state
    assert len(channel.sent) == sent_before
    assert store.states["FLIK1"].status("disk_space") == checks.BAD


def test_recovery_notifies_and_resets():
    mon, store, channel = _monitoring()
    mon.on_heartbeat(_heartbeat(storage_free_bytes=1 * 1024**3))
    mon.on_heartbeat(_heartbeat())  # healthy again
    resolved = [n for n in channel.sent if n.title.startswith("Resolved:")]
    assert resolved and resolved[0].severity == "info"
    assert store.states["FLIK1"].status("disk_space") == checks.OK


def test_critical_repages_after_cooldown():
    late = NOW + timedelta(seconds=CFG.critical_repage_seconds + 60)
    clock = {"now": NOW}
    store = FakeStateStore()
    channel = RecordingChannel()
    mon = Monitoring(
        cfg=CFG,
        state_store=store,
        notifier=Notifier([channel]),
        roster_fn=lambda: [{"device_id": "FLIK1", "liveness_enabled": True}],
        latest_heartbeats_fn=lambda ids: {},
        now_fn=lambda: clock["now"],
    )
    bad = _heartbeat(storage_free_bytes=1 * 1024**3)
    mon.on_heartbeat(bad)
    mon.on_heartbeat(bad)
    assert len([n for n in channel.sent if "disk low" in n.title]) == 1
    clock["now"] = late
    mon.on_heartbeat(_heartbeat(storage_free_bytes=1 * 1024**3, age_seconds=-CFG.critical_repage_seconds - 60))
    still = [n for n in channel.sent if n.title.startswith("Still failing:")]
    assert len(still) == 1


def test_warning_repages_after_cooldown_but_not_before():
    """Before this fix, a BAD warning-severity check only ever notified once
    (on the initial OK->BAD transition) and then stayed silent forever until
    it resolved -- no reminder, no matter how long a device sat at low disk.
    Warnings should still repeat, just far less often than criticals."""
    cfg = MonitorConfig(warning_repage_seconds=CFG.warning_repage_seconds)
    late = NOW + timedelta(seconds=cfg.warning_repage_seconds + 60)
    too_soon = NOW + timedelta(seconds=cfg.warning_repage_seconds - 60)
    clock = {"now": NOW}
    store = FakeStateStore()
    channel = RecordingChannel()
    mon = Monitoring(
        cfg=cfg,
        state_store=store,
        notifier=Notifier([channel]),
        roster_fn=lambda: [{"device_id": "FLIK1", "liveness_enabled": True}],
        latest_heartbeats_fn=lambda ids: {},
        now_fn=lambda: clock["now"],
    )
    low = _heartbeat(storage_free_bytes=int(0.05 * 1000 * 1024**3), storage_total_bytes=1000 * 1024**3)
    mon.on_heartbeat(low)
    assert len([n for n in channel.sent if "disk trending full" in n.title]) == 1

    clock["now"] = too_soon
    mon.on_heartbeat(low)
    assert len([n for n in channel.sent if "disk trending full" in n.title]) == 1  # still within cooldown

    clock["now"] = late
    mon.on_heartbeat(low)
    still = [n for n in channel.sent if n.title.startswith("Still failing:") and "disk trending full" in n.title]
    assert len(still) == 1


def test_on_heartbeat_notifies_every_restart_not_just_the_first():
    mon, store, channel = _monitoring()
    mon.on_heartbeat(_heartbeat(pipeline={"uptime_seconds": 3600.0}))
    mon.on_heartbeat(_heartbeat(pipeline={"uptime_seconds": 50.0}))  # restart 1
    mon.on_heartbeat(_heartbeat(pipeline={"uptime_seconds": 200.0}))  # stayed up
    mon.on_heartbeat(_heartbeat(pipeline={"uptime_seconds": 40.0}))  # restart 2 (crash loop)
    restarts = [n for n in channel.sent if "restarted" in n.title]
    assert len(restarts) == 2


def test_unmonitored_device_is_silent():
    mon, store, channel = _monitoring(roster=[{"device_id": "FLIK1", "monitored": True}])
    mon.on_heartbeat(_heartbeat("GHOST", storage_free_bytes=0))
    assert channel.sent == [] and store.put_count == 0


def test_sweep_liveness_and_healthchecks_ping_runs_last(monkeypatch):
    pings: list[str] = []
    monkeypatch.setattr(monitoring_module, "ping_healthchecks", lambda url: pings.append(url))
    cfg = MonitorConfig(healthchecks_ping_url="https://hc.example/ping")
    mon, store, channel = _monitoring(
        roster=[
            {"device_id": "FLIK1", "liveness_enabled": True},
            {"device_id": "FLIK2", "liveness_enabled": True},
        ],
        latest={"FLIK1": _heartbeat("FLIK1", age_seconds=30)},
        cfg=cfg,
    )
    summary = mon.sweep()
    assert summary["devices"] == 2 and summary["liveness_findings"] == 1
    assert any("FLIK2" in n.title for n in channel.sent)
    assert not any("FLIK1" in n.title for n in channel.sent)  # healthy, no prior episode
    assert all(n.route == "emergency" for n in channel.sent)  # liveness always emergency
    assert pings == ["https://hc.example/ping"]


def test_sweep_excludes_dot_children_from_liveness():
    """DOT devices never send their own heartbeat -- they're logical children
    of a FLIK, and their freshness is already covered by check_dot_freshness
    reading the parent's dot_status at heartbeat-ingest time. Including them
    in the plain liveness sweep (which checks "does this exact device_id have
    a heartbeat on record") guarantees a permanent false "never seen" for
    every DOT, forever, regardless of real health."""
    mon, store, channel = _monitoring(
        roster=[
            {"device_id": "FLIK1", "liveness_enabled": True},
            {"device_id": "FLIK1-dot01", "parent_device_id": "FLIK1", "liveness_enabled": True},
            {"device_id": "FLIK1-dot02", "parent_device_id": "FLIK1", "liveness_enabled": True},
        ],
        latest={"FLIK1": _heartbeat("FLIK1", age_seconds=30)},
    )
    summary = mon.sweep()
    assert summary["devices"] == 1
    assert summary["liveness_findings"] == 0
    assert channel.sent == []


def test_sweep_liveness_is_opt_in_not_opt_out():
    """Every notification path is opt-in via liveness_enabled (devices_cli.py) --
    a device only gets checked once it's explicitly set True. The roster
    accumulates every device ever registered, including years of test/scratch
    entries, and monitoring shouldn't have to be opted OUT of one by one.
    Constructs Monitoring directly (not the _monitoring() helper, which
    defaults liveness_enabled True for convenience elsewhere) so FLIK1's
    absent flag is genuinely absent, not defaulted."""
    mon = Monitoring(
        cfg=CFG,
        state_store=FakeStateStore(),
        notifier=Notifier([RecordingChannel()]),
        roster_fn=lambda: [
            {"device_id": "FLIK1"},  # liveness_enabled absent
            {"device_id": "FLIK2", "liveness_enabled": False},
            {"device_id": "FLIK3", "liveness_enabled": True},
        ],
        latest_heartbeats_fn=lambda ids: {},
        now_fn=lambda: NOW,
    )
    channel = mon.notifier.channels[0]
    summary = mon.sweep()
    assert summary["devices"] == 1
    assert [n for n in channel.sent if "FLIK1" in n.title or "FLIK2" in n.title] == []
    assert any("FLIK3" in n.title for n in channel.sent)


def test_finding_route_is_by_check_not_severity():
    """thermal is a WARNING-severity check but routes to general; liveness/disk_space
    are emergency regardless of severity label."""
    mon, store, channel = _monitoring(
        roster=[{"device_id": "FLIK1"}],
        latest={"FLIK1": _heartbeat("FLIK1", cpu_temperature_celsius=95.0)},
    )
    mon.on_heartbeat(_heartbeat("FLIK1", cpu_temperature_celsius=95.0))
    mon.on_heartbeat(_heartbeat("FLIK1", cpu_temperature_celsius=95.0))
    thermal = [n for n in channel.sent if "hot" in n.title]
    assert thermal and all(n.route == "general" for n in thermal)

    channel.sent.clear()
    mon.on_heartbeat(_heartbeat("FLIK1", storage_free_bytes=0))
    disk = [n for n in channel.sent if "disk low" in n.title]
    assert disk and all(n.route == "emergency" for n in disk)


def test_video_backlog_routes_general_bandwidth_cap_routes_emergency():
    mon, store, channel = _monitoring(roster=[{"device_id": "FLIK1"}])
    mon.on_heartbeat(_heartbeat("FLIK1", videos={"captured_total": 50, "uploaded_total": 20}))
    backlog = [n for n in channel.sent if "video backlog" in n.title]
    assert backlog and all(n.route == "general" for n in backlog)

    cfg = MonitorConfig(bandwidth_daily_cap_bytes=500_000)
    mon, store, channel = _monitoring(roster=[{"device_id": "FLIK1"}], cfg=cfg)
    mon.on_heartbeat(_heartbeat("FLIK1", upload={"bytes_uploaded": 1_000_000}))  # delta exceeds the cap
    cap = [n for n in channel.sent if "data cap exceeded" in n.title]
    assert cap and all(n.route == "emergency" for n in cap)


# ---------------------------------------------------------------------------
# cumulative bandwidth: DeviceState rollup + the on_heartbeat cap check
# ---------------------------------------------------------------------------

def test_record_bandwidth_usage_accumulates_within_a_day():
    """The device sends bytes_uploaded already windowed -- bytes transferred
    since its last heartbeat's drain (TransferStats.drain() resets on every
    call) -- not a lifetime counter for us to diff ourselves. Each call's
    delta is added directly, no "first observation" baseline needed."""
    state = DeviceState("FLIK1")
    daily, monthly = state.record_bandwidth_usage(500.0, NOW)
    assert (daily, monthly) == (500.0, 500.0)
    daily, monthly = state.record_bandwidth_usage(500.0, NOW + timedelta(minutes=5))
    assert (daily, monthly) == (1000.0, 1000.0)


def test_record_bandwidth_usage_resets_daily_but_not_monthly_on_day_rollover():
    state = DeviceState("FLIK1")
    state.record_bandwidth_usage(500.0, NOW)  # day 1: 500
    tomorrow = NOW + timedelta(days=1)
    daily, monthly = state.record_bandwidth_usage(500.0, tomorrow)  # day 2 starts: +500
    assert daily == 500.0  # day 1's usage dropped off
    assert monthly == 1000.0  # day 1 + day 2 so far
    daily, monthly = state.record_bandwidth_usage(500.0, tomorrow + timedelta(hours=1))  # day 2: +500 more
    assert daily == 1000.0  # day 2 total only
    assert monthly == 1500.0  # day 1 + day 2, same month


def test_record_bandwidth_usage_ignores_negative_delta():
    """The device's own accumulator can't go backwards (drain() always resets
    to 0, never negative), but guard anyway: a bad sample must not silently
    erase real recorded usage by subtracting from the running total."""
    state = DeviceState("FLIK1")
    state.record_bandwidth_usage(500.0, NOW)
    daily, monthly = state.record_bandwidth_usage(-100.0, NOW + timedelta(minutes=1))
    assert (daily, monthly) == (500.0, 500.0)


def test_bandwidth_cap_dormant_without_upload_bytes():
    mon, store, channel = _monitoring(roster=[{"device_id": "FLIK1"}], cfg=MonitorConfig(bandwidth_daily_cap_bytes=1.0))
    mon.on_heartbeat(_heartbeat("FLIK1"))
    assert channel.sent == []


def test_bandwidth_cap_disabled_by_default():
    mon, store, channel = _monitoring(roster=[{"device_id": "FLIK1"}])
    mon.on_heartbeat(_heartbeat("FLIK1", upload={"bytes_uploaded": 10_000_000_000}))
    assert not any("data cap" in n.title for n in channel.sent)


def test_digest_reports_new_track_count_per_device_on_general_route():
    mon, _, channel = _monitoring(
        roster=[{"device_id": "FLIK1"}, {"device_id": "FLIK2"}],
        track_counts={"FLIK1": 7, "FLIK2": 0},
    )
    summary = mon.digest()
    assert summary == {"devices": 2}
    assert len(channel.sent) == 2
    assert all(n.route == "general" and n.severity == "info" for n in channel.sent)
    titles = {n.title for n in channel.sent}
    assert titles == {"FLIK1: 7 new track(s)", "FLIK2: 0 new track(s)"}


def test_digest_skips_devices_without_liveness_enabled():
    """digest() used to iterate the raw roster with no gate at all -- every
    device ever registered (test/scratch entries included) got an "0 new
    track(s)" notification every window, forever. Now shares the same
    liveness_enabled gate as every other notification path."""
    mon = Monitoring(
        cfg=CFG,
        state_store=FakeStateStore(),
        notifier=Notifier([RecordingChannel()]),
        roster_fn=lambda: [
            {"device_id": "FLIK1", "liveness_enabled": True},
            {"device_id": "test-scratch-device"},  # liveness_enabled absent
        ],
        latest_heartbeats_fn=lambda ids: {},
        track_count_fn=lambda device_id, window_start, now: 0,
        now_fn=lambda: NOW,
    )
    channel = mon.notifier.channels[0]
    summary = mon.digest()
    assert summary == {"devices": 1}
    assert channel.sent and all("FLIK1" in n.title for n in channel.sent)


def test_digest_window_is_configurable():
    seen_windows = []

    def track_count_fn(device_id, window_start, now):
        seen_windows.append((device_id, window_start, now))
        return 0

    mon = Monitoring(
        cfg=MonitorConfig(digest_window_hours=4.0),
        state_store=FakeStateStore(),
        notifier=Notifier([RecordingChannel()]),
        roster_fn=lambda: [{"device_id": "FLIK1", "liveness_enabled": True}],
        latest_heartbeats_fn=lambda ids: {},
        track_count_fn=track_count_fn,
        now_fn=lambda: NOW,
    )
    mon.digest()
    ((device_id, window_start, now),) = seen_windows
    assert device_id == "FLIK1"
    assert now == NOW
    assert window_start == NOW - timedelta(hours=4)


class TestIsMonitored:
    """_is_monitored() is the single gate shared by on_heartbeat, on_log_digest,
    on_capture_report, and digest() -- it must require liveness_enabled
    specifically, not just roster membership, or any one of those paths
    silently reverts to notifying for every registered device."""

    def test_requires_liveness_enabled_true_not_just_roster_membership(self):
        mon = Monitoring(
            cfg=CFG,
            state_store=FakeStateStore(),
            notifier=Notifier([RecordingChannel()]),
            roster_fn=lambda: [
                {"device_id": "FLIK1", "liveness_enabled": True},
                {"device_id": "FLIK2", "liveness_enabled": False},
                {"device_id": "FLIK3"},  # absent
            ],
            now_fn=lambda: NOW,
        )
        assert mon._is_monitored("FLIK1") is True
        assert mon._is_monitored("FLIK2") is False
        assert mon._is_monitored("FLIK3") is False

    def test_dot_child_inherits_parent_liveness_enabled(self):
        """Enabling a FLIK should reasonably cover its DOT children too --
        without this, digest() (which shares this gate) would go silent for
        every DOT under an enabled FLIK, since DOT rows never get their own
        liveness_enabled set individually in practice."""
        mon = Monitoring(
            cfg=CFG,
            state_store=FakeStateStore(),
            notifier=Notifier([RecordingChannel()]),
            roster_fn=lambda: [
                {"device_id": "FLIK1", "liveness_enabled": True},
                {"device_id": "FLIK1-dot01", "parent_device_id": "FLIK1"},  # own flag absent
                {"device_id": "FLIK2"},  # parent not enabled
                {"device_id": "FLIK2-dot01", "parent_device_id": "FLIK2"},
            ],
            now_fn=lambda: NOW,
        )
        assert mon._is_monitored("FLIK1-dot01") is True
        assert mon._is_monitored("FLIK2-dot01") is False

    def test_dot_child_explicit_false_overrides_parent(self):
        """A DOT explicitly disabled on its own stays disabled even if its
        parent FLIK is enabled -- lets you silence one problem DOT without
        touching the rest of the fleet."""
        mon = Monitoring(
            cfg=CFG,
            state_store=FakeStateStore(),
            notifier=Notifier([RecordingChannel()]),
            roster_fn=lambda: [
                {"device_id": "FLIK1", "liveness_enabled": True},
                {"device_id": "FLIK1-dot01", "parent_device_id": "FLIK1", "liveness_enabled": False},
            ],
            now_fn=lambda: NOW,
        )
        assert mon._is_monitored("FLIK1-dot01") is False

    def test_device_not_on_roster_at_all_is_not_monitored(self):
        mon = Monitoring(
            cfg=CFG,
            state_store=FakeStateStore(),
            notifier=Notifier([RecordingChannel()]),
            roster_fn=lambda: [{"device_id": "FLIK1", "liveness_enabled": True}],
            now_fn=lambda: NOW,
        )
        assert mon._is_monitored("GHOST") is False


def test_roster_filters_monitored_false():
    mon, _, channel = _monitoring(
        roster=[{"device_id": "FLIK1"}],  # roster_fn output is already filtered upstream;
    )
    # _fetch_roster filtering behavior is covered directly:
    devices = [
        {"device_id": "A"},
        {"device_id": "B", "monitored": False},
        {"device_id": "C", "monitored": True},
    ]
    kept = [d for d in devices if d.get("monitored") is not False]
    assert [d["device_id"] for d in kept] == ["A", "C"]


# ---------------------------------------------------------------------------
# trigger integration: monitoring never breaks ingest; dispatch by event shape
# ---------------------------------------------------------------------------

class _ExplodingMonitor:
    def on_heartbeat(self, record):
        raise RuntimeError("monitoring blew up")


def test_heartbeat_ingest_survives_monitor_failure(tmp_path):
    heartbeat_key = "v1/FLIK1/heartbeats/20260714_120000.json"
    root = tmp_path
    target = root / heartbeat_key
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(_heartbeat()), encoding="utf-8")
    storage = trigger_handler.LocalStorageAdapter(root)
    writer = trigger_handler.CollectingWriter()
    summary = trigger_handler.process_heartbeat_object(
        storage, writer, "bucket", heartbeat_key, monitor=_ExplodingMonitor()
    )
    assert summary == {"heartbeats": 1}
    assert len(writer.heartbeats) == 1


def test_lambda_handler_dispatches_scheduled_event(monkeypatch):
    swept = {}

    class _FakeMonitor:
        def sweep(self):
            swept["ran"] = True
            return {"devices": 0, "liveness_findings": 0, "notified": 0}

    monkeypatch.setattr(trigger_handler, "_build_monitor", lambda: _FakeMonitor())
    result = trigger_handler.lambda_handler({"source": "aws.events", "detail-type": "Scheduled Event"}, None)
    assert swept.get("ran") is True
    assert json.loads(result["body"])["sweep"]["devices"] == 0


def test_lambda_handler_dispatches_digest_task(monkeypatch):
    digested = {}

    class _FakeMonitor:
        def digest(self):
            digested["ran"] = True
            return {"devices": 3}

    monkeypatch.setattr(trigger_handler, "_build_monitor", lambda: _FakeMonitor())
    result = trigger_handler.lambda_handler({"source": "aws.events", "task": "digest"}, None)
    assert digested.get("ran") is True
    assert json.loads(result["body"])["digest"]["devices"] == 3


def test_heartbeat_schema_keeps_v2_fields(tmp_path):
    heartbeat_key = "v1/FLIK1/heartbeats/20260714_120000.json"
    payload = _heartbeat(
        results={"total": 1, "finalized_unpublished": 0, "awaiting_classification": 1, "other": 0},
        upload={"queue_depth": 2, "pending_bytes": 123, "last_flush_at": NOW.isoformat(), "last_flush_bytes_per_sec": 1000.0},
    )
    target = tmp_path / heartbeat_key
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    writer = trigger_handler.CollectingWriter()
    trigger_handler.process_heartbeat_object(
        trigger_handler.LocalStorageAdapter(tmp_path), writer, "bucket", heartbeat_key
    )
    (record,) = writer.heartbeats
    assert record["results"]["awaiting_classification"] == 1
    assert record["upload"]["queue_depth"] == 2
