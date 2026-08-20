"""Notification delivery: channel plug-ins behind one Notifier.

Channels register only when configured (env var set), so adding a new transport
is a new class plus one env var — no changes to callers. Send failures are
logged and swallowed: notification delivery must never fail heartbeat ingest.

Routing: each Notification carries a ``route`` ("emergency" | "general"),
independent of severity — a warning-level check can still be an emergency
(e.g. log errors), and a resolved/info notice for a critical check still
belongs on the emergency route it originated from. Channels built with a
``route`` only receive notifications on that route; a channel with no route
(e.g. a bare test fake) receives everything, which keeps single-channel test
fixtures working unchanged.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from monitor_config import MonitorConfig

SEND_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Notification:
    severity: str  # critical | warning | info
    title: str
    body: str
    key: str  # idempotency/context key, e.g. "FLIK4/liveness"
    route: str = "general"  # emergency | general
    image_url: Optional[str] = None  # short-lived presigned URL; channels fetch/reference, never receive bytes


class Channel(Protocol):
    def send(self, notification: Notification) -> None: ...


class NtfyChannel:
    """POST to an ntfy topic URL (https://ntfy.sh/<topic> or self-hosted)."""

    _PRIORITY = {"critical": "urgent", "warning": "default", "info": "low"}
    _TAGS = {"critical": "rotating_light", "warning": "warning", "info": "white_check_mark"}

    def __init__(self, topic_url: str, route: Optional[str] = None) -> None:
        self.topic_url = topic_url
        self.route = route

    def send(self, notification: Notification) -> None:
        headers = {
            "Title": notification.title,
            "Priority": self._PRIORITY.get(notification.severity, "default"),
            "Tags": self._TAGS.get(notification.severity, "warning"),
        }
        if notification.image_url:
            # ntfy fetches and attaches the file itself; body becomes the caption.
            headers["Attach"] = notification.image_url
        request = urllib.request.Request(
            self.topic_url,
            data=notification.body.encode("utf-8"),
            method="POST",
            headers=headers,
        )
        urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS)


class SlackChannel:
    """POST to a Slack incoming webhook URL."""

    _EMOJI = {"critical": ":rotating_light:", "warning": ":warning:", "info": ":white_check_mark:"}

    def __init__(self, webhook_url: str, route: Optional[str] = None) -> None:
        self.webhook_url = webhook_url
        self.route = route

    def send(self, notification: Notification) -> None:
        emoji = self._EMOJI.get(notification.severity, ":warning:")
        text = f"{emoji} *{notification.title}*\n{notification.body}"
        payload: Dict[str, Any] = {"text": text}
        if notification.image_url:
            payload["blocks"] = [
                {"type": "section", "text": {"type": "mrkdwn", "text": text}},
                {"type": "image", "image_url": notification.image_url, "alt_text": notification.title},
            ]
        request = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS)


class Notifier:
    def __init__(self, channels: List[Any]) -> None:
        self.channels = channels

    def notify(self, notification: Notification) -> None:
        for channel in self.channels:
            channel_route = getattr(channel, "route", None)
            if channel_route is not None and channel_route != notification.route:
                continue
            try:
                channel.send(notification)
            except Exception as exc:  # delivery must never break processing
                print(
                    "Notify failed via "
                    f"{type(channel).__name__} for {notification.key}: {exc}"
                )


def build_notifier(cfg: MonitorConfig) -> Notifier:
    channels: List[Any] = []
    if cfg.ntfy_emergency_url:
        channels.append(NtfyChannel(cfg.ntfy_emergency_url, route="emergency"))
    if cfg.ntfy_general_url:
        channels.append(NtfyChannel(cfg.ntfy_general_url, route="general"))
    if cfg.slack_emergency_url:
        channels.append(SlackChannel(cfg.slack_emergency_url, route="emergency"))
    if cfg.slack_general_url:
        channels.append(SlackChannel(cfg.slack_general_url, route="general"))
    if not channels:
        print(
            "Notifier: no channels configured (set MONITOR_NTFY_EMERGENCY_URL, "
            "MONITOR_NTFY_GENERAL_URL, MONITOR_SLACK_EMERGENCY_URL, or "
            "MONITOR_SLACK_GENERAL_URL); notifications will be logged only"
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
