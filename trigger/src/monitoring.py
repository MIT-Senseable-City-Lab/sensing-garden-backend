"""Trigger-resident fleet monitoring orchestration.

Two entry points, both invoked from trigger_handler and both wrapped there so a
monitoring failure can never fail S3 ingest:

- ``on_heartbeat(record)``: content checks against the fresh payload at ingest
  (disk, thermal, DOT freshness, results backlog, bandwidth).
- ``sweep()``: EventBridge-scheduled liveness pass — absence of heartbeats is
  not an S3 event, so only a clock can detect it. Ends with the Healthchecks
  dead-man ping (last statement: a partially failed sweep must not report
  healthy).

Notification policy lives in ``_apply``: page on OK->BAD, page recovery on
BAD->OK, re-page criticals still bad after ``critical_repage_seconds``.
Because state transitions persist alongside ``last_notified_at``, a retried S3
event re-runs the checks but finds the state already BAD and stays silent.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from checks import BAD, CRITICAL, OK, Finding, _human_bytes, check_liveness, extract_samples, run_content_checks
from monitor_config import MonitorConfig
from monitor_state import DeviceState, MonitorStateStore
from notify import Notification, Notifier, build_notifier, ping_healthchecks

DEVICES_TABLE = os.environ.get("DEVICES_TABLE", "sensing-garden-devices")
HEARTBEATS_TABLE = os.environ.get("HEARTBEATS_TABLE", "sensing-garden-heartbeats")
TRACKS_TABLE = os.environ.get("TRACKS_TABLE", "sensing-garden-tracks")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")

ROSTER_CACHE_SECONDS = 300
BACKDROP_URL_TTL_SECONDS = 300

# Route is a policy decision independent of severity: a warning-level check can
# still be an emergency (log errors), and "still failing"/recovery notices for
# a check always follow that check's route. Unlisted checks default to general.
EMERGENCY_CHECKS = frozenset({"liveness", "disk_space", "log_errors", "bandwidth_cap"})


def _route_for(check: str) -> str:
    return "emergency" if check in EMERGENCY_CHECKS else "general"


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class Monitoring:
    def __init__(
        self,
        cfg: Optional[MonitorConfig] = None,
        state_store: Optional[MonitorStateStore] = None,
        notifier: Optional[Notifier] = None,
        roster_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        latest_heartbeats_fn: Optional[Callable[[List[str]], Dict[str, Dict[str, Any]]]] = None,
        track_count_fn: Optional[Callable[[str, datetime, datetime], int]] = None,
        backdrop_key_fn: Optional[Callable[[str], Optional[str]]] = None,
        presign_fn: Optional[Callable[[str], str]] = None,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self.cfg = cfg or MonitorConfig.from_env()
        self.state_store = state_store or MonitorStateStore()
        self.notifier = notifier or build_notifier(self.cfg)
        self._roster_fn = roster_fn or self._fetch_roster
        self._latest_heartbeats_fn = latest_heartbeats_fn or self._fetch_latest_heartbeats
        self._track_count_fn = track_count_fn or self._count_tracks_since
        self._backdrop_key_fn = backdrop_key_fn or self._latest_dot_background_key
        self._presign_fn = presign_fn or self._presign_url
        self._now_fn = now_fn
        self._roster_cache: Optional[List[Dict[str, Any]]] = None
        self._roster_cached_at = 0.0
        self._dynamodb = None
        self._s3 = None

    # -- data access -------------------------------------------------------

    @property
    def dynamodb(self) -> Any:
        if self._dynamodb is None:
            self._dynamodb = boto3.resource("dynamodb")
        return self._dynamodb

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            self._s3 = boto3.client("s3")
        return self._s3

    def _fetch_roster(self) -> List[Dict[str, Any]]:
        """All devices with monitoring on: ``monitored`` absent or truthy."""
        table = self.dynamodb.Table(DEVICES_TABLE)
        devices: List[Dict[str, Any]] = []
        kwargs: Dict[str, Any] = {}
        while True:
            response = table.scan(**kwargs)
            devices.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        return [d for d in devices if d.get("monitored") is not False]

    def _fetch_latest_heartbeats(self, device_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        table = self.dynamodb.Table(HEARTBEATS_TABLE)
        latest: Dict[str, Dict[str, Any]] = {}
        for device_id in device_ids:
            response = table.query(
                KeyConditionExpression=Key("device_id").eq(device_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get("Items", [])
            if items:
                latest[device_id] = items[0]
        return latest

    def _count_tracks_since(self, device_id: str, window_start: datetime, now: datetime) -> int:
        table = self.dynamodb.Table(TRACKS_TABLE)
        kwargs: Dict[str, Any] = {
            "IndexName": "device_id_index",
            "KeyConditionExpression": Key("device_id").eq(device_id)
            & Key("timestamp").between(window_start.isoformat(), now.isoformat()),
            "Select": "COUNT",
        }
        count = 0
        while True:
            response = table.query(**kwargs)
            count += response.get("Count", 0)
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        return count

    def _latest_dot_background_key(self, device_id: str) -> Optional[str]:
        """Newest DOT background frame under the device's prefix, by S3
        LastModified — robust to whatever batch/date sub-prefix a device uses,
        since we don't track that structure elsewhere. Devices with no DOT (or
        none yet uploaded) simply have no matching object; that's not an error."""
        if not OUTPUT_BUCKET:
            return None
        paginator = self.s3.get_paginator("list_objects_v2")
        latest_key: Optional[str] = None
        latest_modified = None
        for page in paginator.paginate(Bucket=OUTPUT_BUCKET, Prefix=f"v1/{device_id}/"):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.endswith("_background.jpg") and not key.endswith("current_background.jpg"):
                    continue
                if latest_modified is None or item["LastModified"] > latest_modified:
                    latest_modified = item["LastModified"]
                    latest_key = key
        return latest_key

    def _presign_url(self, key: str) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": OUTPUT_BUCKET, "Key": key},
            ExpiresIn=BACKDROP_URL_TTL_SECONDS,
        )

    def roster(self) -> List[Dict[str, Any]]:
        if self._roster_cache is None or time.monotonic() - self._roster_cached_at > ROSTER_CACHE_SECONDS:
            self._roster_cache = self._roster_fn()
            self._roster_cached_at = time.monotonic()
        return self._roster_cache

    def _is_monitored(self, device_id: str) -> bool:
        return any(str(d.get("device_id")) == device_id for d in self.roster())

    # -- entry points ------------------------------------------------------

    def on_heartbeat(self, record: Dict[str, Any]) -> None:
        """Content checks on one freshly ingested heartbeat."""
        device_id = str(record.get("device_id", ""))
        if not device_id or not self._is_monitored(device_id):
            return
        now = self._now_fn()
        state = self.state_store.get(device_id)
        state.record_sample(extract_samples(record))
        findings = run_content_checks(device_id, record, state.samples, now, self.cfg)
        bandwidth_cap = self._bandwidth_cap_finding(device_id, record, state, now)
        if bandwidth_cap is not None:
            findings.append(bandwidth_cap)
        self._apply(findings, state, now)
        self.state_store.put(state, now)

    def _bandwidth_cap_finding(
        self, device_id: str, record: Dict[str, Any], state: DeviceState, now: datetime
    ) -> Optional[Finding]:
        """Cumulative daily/monthly usage against a cell data cap. Not a
        history-window check like the others -- rolls the device's own delta
        (bytes_uploaded, already windowed since its last heartbeat -- see
        Pollen.stats()/TransferStats.drain()) into running totals persisted
        on DeviceState, since day/month spans far outsize the bounded sample
        window. Dormant until devices send upload.bytes_uploaded; caps of 0
        mean "disabled"."""
        upload = record.get("upload")
        delta = upload.get("bytes_uploaded") if isinstance(upload, dict) else None
        if delta is None:
            return None
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            return None
        daily_bytes, monthly_bytes = state.record_bandwidth_usage(delta, now)
        daily_cap = self.cfg.bandwidth_daily_cap_bytes
        monthly_cap = self.cfg.bandwidth_monthly_cap_bytes
        over_daily = daily_cap > 0 and daily_bytes > daily_cap
        over_monthly = monthly_cap > 0 and monthly_bytes > monthly_cap
        if over_daily or over_monthly:
            parts = []
            if over_daily:
                parts.append(f"{_human_bytes(daily_bytes)} today (cap {_human_bytes(daily_cap)})")
            if over_monthly:
                parts.append(f"{_human_bytes(monthly_bytes)} this month (cap {_human_bytes(monthly_cap)})")
            return Finding(device_id, "bandwidth_cap", BAD, CRITICAL, f"{device_id}: data cap exceeded", "; ".join(parts))
        return Finding(
            device_id, "bandwidth_cap", OK, CRITICAL, f"{device_id}: data usage OK",
            f"{_human_bytes(daily_bytes)} today, {_human_bytes(monthly_bytes)} this month",
        )

    def sweep(self) -> Dict[str, int]:
        """Scheduled liveness pass. Returns a small summary for the Lambda response.

        Opt-in, not opt-out: only devices with liveness_enabled explicitly True
        get checked (toggle via devices_cli.py). The roster accumulates every
        device ever registered -- years of test/scratch entries alongside real
        fleet devices -- so alerting-by-default means opting OUT of every junk
        entry one at a time; opt-in means the alert list only ever contains
        devices someone deliberately turned on.

        Also excludes DOT children (parent_device_id set) regardless of the
        flag: DOTs never send their own heartbeat, so checking their device_id
        against the heartbeats table would always find nothing -- a permanent
        false "never seen" regardless of real health. Their freshness is
        already covered by check_dot_freshness, which reads the parent FLIK's
        dot_status at heartbeat-ingest time. digest()/post_backdrops() still
        iterate the full roster (monitored flag only, no liveness_enabled
        requirement) including DOTs, since tracks and backdrops are correctly
        attributed per-DOT (source_device)."""
        now = self._now_fn()
        roster = [
            d for d in self.roster()
            if d.get("liveness_enabled") is True and not d.get("parent_device_id")
        ]
        device_ids = [str(d.get("device_id")) for d in roster if d.get("device_id")]
        latest = self._latest_heartbeats_fn(device_ids)
        findings = check_liveness(roster, latest, now, self.cfg)
        notified = 0
        for finding in findings:
            state = self.state_store.get(finding.device_id)
            notified += self._apply([finding], state, now)
            self.state_store.put(state, now)
        # Dead-man ping is deliberately the last statement of the sweep.
        ping_healthchecks(self.cfg.healthchecks_ping_url)
        return {"devices": len(device_ids), "liveness_findings": sum(f.status == BAD for f in findings),
                "notified": notified}

    def digest(self) -> Dict[str, int]:
        """Scheduled per-device stats report: new tracks in the trailing window.
        Not a check — always sends, no OK/BAD episode, no cooldown; the window is
        fixed (now - digest_window_hours) rather than since-last-run, so a missed
        or delayed invocation just reports on a slightly different span."""
        now = self._now_fn()
        window_start = now - timedelta(hours=self.cfg.digest_window_hours)
        sent = 0
        for device in self.roster():
            device_id = str(device.get("device_id", ""))
            if not device_id:
                continue
            count = self._track_count_fn(device_id, window_start, now)
            self.notifier.notify(
                Notification(
                    severity="info",
                    title=f"{device_id}: {count} new track(s)",
                    body=f"Last {self.cfg.digest_window_hours:.0f}h ({window_start.isoformat()} to {now.isoformat()})",
                    key=f"{device_id}/digest/{now.isoformat()}",
                    route="general",
                )
            )
            sent += 1
        return {"devices": sent}

    def post_backdrops(self) -> Dict[str, int]:
        """Scheduled DOT backdrop post: the most recent no-insects reference frame
        per device, so a human can sanity-check camera framing/focus/lighting
        without waiting for a track. Stateless — always posts whatever is newest;
        devices with no DOT background yet are silently skipped, not an error."""
        sent = 0
        for device in self.roster():
            device_id = str(device.get("device_id", ""))
            if not device_id:
                continue
            key = self._backdrop_key_fn(device_id)
            if key is None:
                continue
            self.notifier.notify(
                Notification(
                    severity="info",
                    title=f"{device_id}: backdrop",
                    body=key.rsplit("/", 1)[-1],
                    key=f"{device_id}/backdrop/{key}",
                    route="general",
                    image_url=self._presign_fn(key),
                )
            )
            sent += 1
        return {"devices": sent}

    def on_alarm(self, event: Dict[str, Any]) -> None:
        """CloudWatch alarm forwarding — filled in by the step-4 rollout."""
        alarm = event.get("alarmData", {})
        print(f"Alarm event received (forwarding not yet implemented): {alarm.get('alarmName', '?')}")

    def on_log_digest(self, digest: Any) -> None:
        """One page per device per cooldown window for error-tagged log lines
        (SPEC item 11). ``log_errors`` is a cooldown-only pseudo-check: shipped
        logs describe finished periods, so there is no OK/BAD episode to track —
        just "this device's logs contain errors, don't repeat it for a while"."""
        device_id = str(digest.device_id)
        if not device_id or not self._is_monitored(device_id):
            return
        now = self._now_fn()
        state = self.state_store.get(device_id)
        last = state.last_notified("log_errors")
        if last is not None and (now - last).total_seconds() < self.cfg.log_error_cooldown_seconds:
            return
        body = f"First: {digest.first_error}"
        if digest.last_error and digest.last_error != digest.first_error:
            body += f"\nLast: {digest.last_error}"
        if digest.traceback_count:
            body += f"\n{digest.traceback_count} traceback(s)"
        self.notifier.notify(
            Notification(
                severity="warning",
                title=f"{device_id}: {digest.error_count} error line(s) in {digest.log_name}",
                body=body,
                key=f"{device_id}/log_errors/{digest.log_name}",
                route=_route_for("log_errors"),
            )
        )
        state.mark_notified("log_errors", now)
        self.state_store.put(state, now)

    # -- notification policy -----------------------------------------------

    def _apply(self, findings: List[Finding], state: DeviceState, now: datetime) -> int:
        notified = 0
        for finding in findings:
            previous = state.status(finding.check)
            if finding.status == BAD:
                if previous != BAD:
                    state.transition(finding.check, BAD, now)
                    self._send(finding, state, resolved=False)
                    state.mark_notified(finding.check, now)
                    notified += 1
                else:
                    repage_seconds = (
                        self.cfg.critical_repage_seconds if finding.severity == "critical"
                        else self.cfg.warning_repage_seconds
                    )
                    last = state.last_notified(finding.check)
                    if last is None or (now - last).total_seconds() >= repage_seconds:
                        self._send(finding, state, resolved=False, still=True)
                        state.mark_notified(finding.check, now)
                        notified += 1
            elif finding.status == OK and previous == BAD:
                state.transition(finding.check, OK, now)
                self._send(finding, state, resolved=True)
                state.mark_notified(finding.check, now)
                notified += 1
        return notified

    def _send(self, finding: Finding, state: DeviceState, *, resolved: bool, still: bool = False) -> None:
        title = finding.title
        if resolved:
            title = f"Resolved: {title}"
            severity = "info"
        elif still:
            title = f"Still failing: {title}"
            severity = finding.severity
        else:
            severity = finding.severity
        self.notifier.notify(
            Notification(
                severity=severity,
                title=title,
                body=finding.body,
                key=f"{finding.device_id}/{finding.check}/{state.since(finding.check)}",
                route=_route_for(finding.check),
            )
        )


_instance: Optional[Monitoring] = None


def get_monitoring() -> Monitoring:
    global _instance
    if _instance is None:
        _instance = Monitoring()
    return _instance
