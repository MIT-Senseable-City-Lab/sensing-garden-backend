from __future__ import annotations

import json
import sys
from pathlib import Path

TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.path.insert(0, str(TRIGGER_SRC))

from monitor_config import MonitorConfig  # noqa: E402
from notify import Notification, SlackChannel, build_notifier  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))


def _notification(severity: str = "critical") -> Notification:
    return Notification(severity=severity, title="FLIK4/liveness", body="No heartbeat for 20m", key="FLIK4/liveness")


def test_slack_channel_posts_json_with_mrkdwn_text(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["headers"] = request.headers
        sent["body"] = json.loads(request.data.decode("utf-8"))
        sent["timeout"] = timeout

    monkeypatch.setattr("notify.urllib.request.urlopen", fake_urlopen)

    SlackChannel("https://hooks.slack.com/services/T0/B0/xyz").send(_notification())

    assert sent["url"] == "https://hooks.slack.com/services/T0/B0/xyz"
    assert sent["headers"]["Content-type"] == "application/json"
    text = sent["body"]["text"]
    assert text.startswith(":rotating_light: *FLIK4/liveness*\n")
    assert "No heartbeat for 20m" in text


def test_slack_channel_severity_emoji():
    assert SlackChannel._EMOJI["critical"] == ":rotating_light:"
    assert SlackChannel._EMOJI["warning"] == ":warning:"
    assert SlackChannel._EMOJI["info"] == ":white_check_mark:"


def test_build_notifier_registers_slack_when_configured():
    notifier = build_notifier(MonitorConfig(slack_webhook_url="https://hooks.slack.com/services/T0/B0/xyz"))
    assert any(isinstance(c, SlackChannel) for c in notifier.channels)


def test_build_notifier_omits_slack_when_unconfigured():
    notifier = build_notifier(MonitorConfig())
    assert not any(isinstance(c, SlackChannel) for c in notifier.channels)
