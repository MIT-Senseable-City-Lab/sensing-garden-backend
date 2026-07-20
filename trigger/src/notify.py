"""Notification delivery: channel plug-ins behind one Notifier.

Channels register only when configured (env var set), so adding Slack later is
a new class plus one env var — no changes to callers. Send failures are logged
and swallowed: notification delivery must never fail heartbeat ingest.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, List, Protocol

from monitor_config import MonitorConfig

SEND_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Notification:
    severity: str  # critical | warning | info
    title: str
    body: str
    key: str  # idempotency/context key, e.g. "FLIK4/liveness"


class Channel(Protocol):
    def send(self, notification: Notification) -> None: ...


class NtfyChannel:
    """POST to an ntfy topic URL (https://ntfy.sh/<topic> or self-hosted)."""

    _PRIORITY = {"critical": "urgent", "warning": "default", "info": "low"}
    _TAGS = {"critical": "rotating_light", "warning": "warning", "info": "white_check_mark"}

    def __init__(self, topic_url: str) -> None:
        self.topic_url = topic_url

    def send(self, notification: Notification) -> None:
        request = urllib.request.Request(
            self.topic_url,
            data=notification.body.encode("utf-8"),
            method="POST",
            headers={
                "Title": notification.title,
                "Priority": self._PRIORITY.get(notification.severity, "default"),
                "Tags": self._TAGS.get(notification.severity, "warning"),
            },
        )
        urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS)


class SlackChannel:
    """POST to a Slack incoming webhook URL."""

    _EMOJI = {"critical": ":rotating_light:", "warning": ":warning:", "info": ":white_check_mark:"}

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, notification: Notification) -> None:
        emoji = self._EMOJI.get(notification.severity, ":warning:")
        text = f"{emoji} *{notification.title}*\n{notification.body}"
        request = urllib.request.Request(
            self.webhook_url,
            data=json.dumps({"text": text}).encode("utf-8"),
            method="POST",
            headers={"Content-type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS)


class Notifier:
    def __init__(self, channels: List[Any]) -> None:
        self.channels = channels

    def notify(self, notification: Notification) -> None:
        for channel in self.channels:
            try:
                channel.send(notification)
            except Exception as exc:  # delivery must never break processing
                print(
                    "Notify failed via "
                    f"{type(channel).__name__} for {notification.key}: {exc}"
                )


def build_notifier(cfg: MonitorConfig) -> Notifier:
    channels: List[Any] = []
    if cfg.ntfy_topic_url:
        channels.append(NtfyChannel(cfg.ntfy_topic_url))
    if cfg.slack_webhook_url:
        channels.append(SlackChannel(cfg.slack_webhook_url))
    if not channels:
        print(
            "Notifier: no channels configured (set MONITOR_NTFY_TOPIC_URL or "
            "MONITOR_SLACK_WEBHOOK_URL); notifications will be logged only"
        )
    return Notifier(channels)


def ping_healthchecks(url: str) -> None:
    """Dead-man ping; last action of a sweep. Log-don't-raise: a failed ping makes
    Healthchecks page, which is fail-loud and correct."""
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=SEND_TIMEOUT_SECONDS)
    except Exception as exc:
        print(f"Healthchecks ping failed: {exc}")
