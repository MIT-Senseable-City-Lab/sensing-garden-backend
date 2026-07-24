"""CLI to toggle per-device liveness-sweep monitoring.

Liveness alerting is opt-in (Monitoring.sweep() only checks devices with
liveness_enabled explicitly True) -- the devices table accumulates every
device ever registered, including years of test/scratch entries, so
alerting-by-default means opting OUT of every junk entry one at a time.
This is the tool for opting real devices IN.
"""
from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional, Sequence

import boto3

DEVICES_TABLE = os.environ.get("DEVICES_TABLE", "sensing-garden-devices")


class DeviceStore:
    def __init__(self, table_name: str = DEVICES_TABLE) -> None:
        self.table = boto3.resource("dynamodb").Table(table_name)

    def list_devices(self) -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = []
        kwargs: Dict[str, Any] = {}
        while True:
            response = self.table.scan(**kwargs)
            devices.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        return devices

    def set_liveness_enabled(self, device_id: str, enabled: bool) -> None:
        self.table.update_item(
            Key={"device_id": device_id},
            UpdateExpression="SET liveness_enabled = :v",
            ExpressionAttributeValues={":v": enabled},
        )


def main(argv: Optional[Sequence[str]] = None, store: Optional[DeviceStore] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    store = store or DeviceStore()
    if args.command == "list":
        _list(store)
    elif args.command == "enable":
        for device_id in args.device_ids:
            store.set_liveness_enabled(device_id, True)
            print(f"{device_id}: liveness ON")
    else:
        for device_id in args.device_ids:
            store.set_liveness_enabled(device_id, False)
            print(f"{device_id}: liveness OFF")
    return 0


def _list(store: DeviceStore) -> None:
    devices = sorted(store.list_devices(), key=lambda d: str(d.get("device_id", "")))
    for device in devices:
        device_id = str(device.get("device_id", "?"))
        liveness = "on" if device.get("liveness_enabled") is True else "off"
        monitored = "off" if device.get("monitored") is False else "on"
        parent = device.get("parent_device_id")
        suffix = f"  (child of {parent})" if parent else ""
        print(f"{device_id:30} liveness={liveness:<4} monitored={monitored:<4}{suffix}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Toggle per-device liveness-sweep monitoring (opt-in; disabled by default)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List all registered devices with liveness/monitored status")

    enable = subparsers.add_parser("enable", help="Turn liveness checks ON for one or more devices")
    enable.add_argument("device_ids", nargs="+")

    disable = subparsers.add_parser("disable", help="Turn liveness checks OFF for one or more devices (also the default)")
    disable.add_argument("device_ids", nargs="+")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
