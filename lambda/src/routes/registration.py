import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import dynamodb
from schemas import DeviceApiKey
from utils import _parse_request, json_response


def _get_setup_code() -> str:
    return os.environ.get("SETUP_CODE", "").strip()


def _build_registration_record(device_name: str) -> Dict[str, str]:
    created = datetime.now(timezone.utc).isoformat()
    return DeviceApiKey(
        device_id=str(uuid.uuid4()),
        api_key=secrets.token_hex(32),
        device_name=device_name,
        created=created,
        status="active",
    ).model_dump()


def handle_register(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        setup_code = str(body.get("setup_code", "")).strip()
        device_name = str(body.get("device_name", "")).strip()

        if not setup_code:
            raise ValueError("setup_code is required")
        if not device_name:
            raise ValueError("device_name is required")
        if setup_code != _get_setup_code():
            return json_response(401, {"error": "Invalid setup code"})

        record = _build_registration_record(device_name)
        try:
            dynamodb.store_device_api_key(record)
            dynamodb.add_device(record["device_id"], record["created"])
        except Exception:
            dynamodb.delete_device_api_key(record["device_id"])
            raise

        return json_response(
            201,
            {
                "device_id": record["device_id"],
                "api_key": record["api_key"],
                "device_name": record["device_name"],
                "created": record["created"],
            },
        )
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
