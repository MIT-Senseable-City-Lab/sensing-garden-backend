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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from checks import BAD, OK, Finding, check_liveness, extract_samples, run_content_checks
from monitor_config import MonitorConfig
from monitor_state import DeviceState, MonitorStateStore
from notify import Notification, Notifier, build_notifier, ping_healthchecks

DEVICES_TABLE = os.environ.get("DEVICES_TABLE", "sensing-garden-devices")
HEARTBEATS_TABLE = os.environ.get("HEARTBEATS_TABLE", "sensing-garden-heartbeats")

ROSTER_CACHE_SECONDS = 300


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
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self.cfg = cfg or MonitorConfig.from_env()
        self.state_store = state_store or MonitorStateStore()
        self.notifier = notifier or build_notifier(self.cfg)
        self._roster_fn = roster_fn or self._fetch_roster
        self._latest_heartbeats_fn = latest_heartbeats_fn or self._fetch_latest_heartbeats
        self._now_fn = now_fn
        self._roster_cache: Optional[List[Dict[str, Any]]] = None
        self._roster_cached_at = 0.0
        self._dynamodb = None

    # -- data access -------------------------------------------------------

    @property
    def dynamodb(self) -> Any:
        if self._dynamodb is None:
            self._dynamodb = boto3.resource("dynamodb")
        return self._dynamodb

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
        self._apply(findings, state, now)
        self.state_store.put(state, now)

    def sweep(self) -> Dict[str, int]:
        """Scheduled liveness pass. Returns a small summary for the Lambda response."""
        now = self._now_fn()
        roster = self.roster()
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

    def on_alarm(self, event: Dict[str, Any]) -> None:
        """CloudWatch alarm forwarding — filled in by the step-4 rollout."""
        alarm = event.get("alarmData", {})
        print(f"Alarm event received (forwarding not yet implemented): {alarm.get('alarmName', '?')}")

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
                elif finding.severity == "critical":
                    last = state.last_notified(finding.check)
                    if last is None or (now - last).total_seconds() >= self.cfg.critical_repage_seconds:
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
            )
        )


_instance: Optional[Monitoring] = None


def get_monitoring() -> Monitoring:
    global _instance
    if _instance is None:
        _instance = Monitoring()
    return _instance
