from __future__ import annotations

import json
import sys
from pathlib import Path

TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.path.insert(0, str(TRIGGER_SRC))

from monitor_config import MonitorConfig  # noqa: E402
from notify import Notification, NtfyChannel, Notifier, SlackChannel, build_notifier  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))


def _notification(severity: str = "critical", route: str = "general", image_url: str | None = None) -> Notification:
    return Notification(
        severity=severity,
        title="FLIK4/liveness",
        body="No heartbeat for 20m",
        key="FLIK4/liveness",
        route=route,
        image_url=image_url,
    )


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
    notifier = build_notifier(MonitorConfig(slack_general_url="https://hooks.slack.com/services/T0/B0/xyz"))
    assert any(isinstance(c, SlackChannel) for c in notifier.channels)


def test_build_notifier_omits_slack_when_unconfigured():
    notifier = build_notifier(MonitorConfig())
    assert not any(isinstance(c, SlackChannel) for c in notifier.channels)


def test_build_notifier_assigns_route_per_configured_url():
    notifier = build_notifier(
        MonitorConfig(
            ntfy_emergency_url="https://ntfy.sh/emergency",
            ntfy_general_url="https://ntfy.sh/general",
            slack_emergency_url="https://hooks.slack.com/emergency",
        )
    )
    routes = {(type(c).__name__, c.route) for c in notifier.channels}
    assert routes == {
        ("NtfyChannel", "emergency"),
        ("NtfyChannel", "general"),
        ("SlackChannel", "emergency"),
    }


def test_notifier_only_sends_to_channels_matching_route(monkeypatch):
    sent_urls = []
    monkeypatch.setattr(
        "notify.urllib.request.urlopen",
        lambda request, timeout: sent_urls.append(request.full_url),
    )

    emergency = NtfyChannel("https://ntfy.sh/emergency", route="emergency")
    general = NtfyChannel("https://ntfy.sh/general", route="general")
    Notifier([emergency, general]).notify(_notification(route="emergency"))

    assert sent_urls == ["https://ntfy.sh/emergency"]


def test_ntfy_channel_attaches_image_url_when_present(monkeypatch):
    requests = []
    monkeypatch.setattr("notify.urllib.request.urlopen", lambda request, timeout: requests.append(request))

    NtfyChannel("https://ntfy.sh/general").send(_notification(image_url="https://s3.example/frame.jpg"))

    assert requests[0].headers["Attach"] == "https://s3.example/frame.jpg"


def test_ntfy_channel_omits_attach_header_without_image_url(monkeypatch):
    requests = []
    monkeypatch.setattr("notify.urllib.request.urlopen", lambda request, timeout: requests.append(request))

    NtfyChannel("https://ntfy.sh/general").send(_notification())

    assert "Attach" not in requests[0].headers


def test_slack_channel_adds_image_block_when_image_url_present(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        "notify.urllib.request.urlopen",
        lambda request, timeout: sent.update(json.loads(request.data.decode("utf-8"))),
    )

    SlackChannel("https://hooks.slack.com/services/T0/B0/xyz").send(
        _notification(image_url="https://s3.example/frame.jpg")
    )

    image_block = next(b for b in sent["blocks"] if b["type"] == "image")
    assert image_block["image_url"] == "https://s3.example/frame.jpg"


def test_slack_channel_omits_blocks_without_image_url(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        "notify.urllib.request.urlopen",
        lambda request, timeout: sent.update(json.loads(request.data.decode("utf-8"))),
    )

    SlackChannel("https://hooks.slack.com/services/T0/B0/xyz").send(_notification())

    assert "blocks" not in sent


def test_notifier_sends_to_routeless_channel_regardless_of_route():
    class FakeChannel:
        def __init__(self):
            self.sent = []

        def send(self, notification):
            self.sent.append(notification)

    channel = FakeChannel()
    Notifier([channel]).notify(_notification(route="emergency"))
    Notifier([channel]).notify(_notification(route="general"))
    assert len(channel.sent) == 2
