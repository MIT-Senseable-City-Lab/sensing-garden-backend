import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict

import dynamodb
from schemas import DeviceApiKey
from utils import _parse_request, json_response


def _get_setup_code() -> str:
    return os.environ.get("SETUP_CODE", "").strip()


def _build_dot_ids(flick_id: str, dot_count: int) -> list[str]:
    return [f"{flick_id}-dot{index:02d}" for index in range(1, dot_count + 1)]


def _parse_dot_count(value: Any) -> int:
    try:
        dot_count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("dot_count must be an integer") from exc
    if dot_count < 0:
        raise ValueError("dot_count must be >= 0")
    return dot_count


def _build_registration_record(
    flick_id: str,
    dot_ids: list[str],
    api_key: str | None = None,
    created: str | None = None,
) -> Dict[str, Any]:
    return DeviceApiKey(
        device_id=flick_id,
        api_key=api_key or secrets.token_hex(32),
        dot_ids=dot_ids,
        created=created or datetime.now(timezone.utc).isoformat(),
        status="active",
    ).model_dump()


def _ensure_registered_devices(flick_id: str, dot_ids: list[str], created: str) -> None:
    dynamodb.upsert_device(flick_id, created=created, parent_device_id=None)
    for dot_id in dot_ids:
        dynamodb.upsert_device(dot_id, created=created, parent_device_id=flick_id)


def handle_register(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        setup_code = str(body.get("setup_code", "")).strip()
        flick_id = str(body.get("flick_id", "")).strip()
        dot_count = _parse_dot_count(body.get("dot_count", 0))

        if not setup_code:
            raise ValueError("setup_code is required")
        if not flick_id:
            raise ValueError("flick_id is required")
        if setup_code != _get_setup_code():
            return json_response(401, {"error": "Invalid setup code"})

        dot_ids = _build_dot_ids(flick_id, dot_count)
        existing_record = dynamodb.get_device_api_key_by_device_id(flick_id)
        record = _build_registration_record(
            flick_id=flick_id,
            dot_ids=dot_ids,
            api_key=existing_record.get("api_key") if existing_record else None,
            created=existing_record.get("created") if existing_record else None,
        )

        try:
            dynamodb.store_device_api_key(record)
            _ensure_registered_devices(flick_id, dot_ids, record["created"])
        except Exception:
            if existing_record is None:
                dynamodb.delete_device_api_key(record["device_id"])
            raise

        return json_response(
            201 if existing_record is None else 200,
            {
                "device_id": record["device_id"],
                "api_key": record["api_key"],
                "flick_id": flick_id,
                "dot_ids": dot_ids,
            },
        )
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
