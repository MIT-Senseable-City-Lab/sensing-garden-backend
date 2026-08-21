from __future__ import annotations

import sys
from pathlib import Path

import pytest

TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

from devices_cli import main  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)


class FakeDeviceStore:
    def __init__(self, devices: list[dict[str, object]]) -> None:
        self.devices = devices
        self.updates: list[tuple[str, bool]] = []

    def list_devices(self) -> list[dict[str, object]]:
        return self.devices

    def set_liveness_enabled(self, device_id: str, enabled: bool) -> None:
        self.updates.append((device_id, enabled))
        for device in self.devices:
            if device.get("device_id") == device_id:
                device["liveness_enabled"] = enabled


def test_enable_sets_liveness_true_for_each_device_id():
    store = FakeDeviceStore([{"device_id": "FLIK2"}, {"device_id": "FLIK4"}])
    main(["enable", "FLIK2", "FLIK4"], store=store)
    assert store.updates == [("FLIK2", True), ("FLIK4", True)]


def test_disable_sets_liveness_false():
    store = FakeDeviceStore([{"device_id": "test-sg1", "liveness_enabled": True}])
    main(["disable", "test-sg1"], store=store)
    assert store.updates == [("test-sg1", False)]


def test_list_prints_liveness_monitored_and_parent_columns(capsys: pytest.CaptureFixture[str]):
    store = FakeDeviceStore([
        {"device_id": "FLIK2", "liveness_enabled": True},
        {"device_id": "FLIK2-dot03", "parent_device_id": "FLIK2"},
        {"device_id": "montreal", "monitored": False},
    ])
    main(["list"], store=store)
    out = capsys.readouterr().out
    assert "FLIK2" in out and "liveness=on" in out
    assert "FLIK2-dot03" in out and "child of FLIK2" in out
    assert "montreal" in out and "monitored=off" in out


def test_enable_requires_at_least_one_device_id():
    store = FakeDeviceStore([])
    with pytest.raises(SystemExit):
        main(["enable"], store=store)
