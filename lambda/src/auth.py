import os
import re
from typing import Any, Dict, Optional, Tuple

import dynamodb


FULL_ACCESS_KEY_ENVS = ("TEST_API_KEY", "EDGE_API_KEY")
READ_ONLY_KEY_ENVS = ("FRONTEND_API_KEY",)
DEPLOYMENTS_API_KEY_ENV = "DEPLOYMENTS_API_KEY"


def _load_configured_keys() -> Dict[str, str]:
    configured_keys: Dict[str, str] = {}
    for key_name in FULL_ACCESS_KEY_ENVS + READ_ONLY_KEY_ENVS + (DEPLOYMENTS_API_KEY_ENV,):
        key_value = os.environ.get(key_name, "").strip()
        if key_value:
            configured_keys[key_name] = key_value
    return configured_keys


CONFIGURED_KEYS = _load_configured_keys()
AuthContext = Dict[str, Any]

READ_ONLY_ALLOWED_GET_PATHS = (
    "/devices",
    "/detections",
    "/detections/count",
    "/classifications",
    "/classifications/count",
    "/classifications/taxa_count",
    "/classifications/time_series",
    "/models",
    "/models/count",
    "/videos",
    "/videos/count",
    "/environment",
    "/environment/count",
    "/environment/time_series",
    "/tracks",
    "/tracks/count",
    "/heartbeats",
    "/export",
    "/deployments",
)

READ_ONLY_ALLOWED_GET_PATTERNS = (
    re.compile(r"^/tracks/[^/]+$"),
    re.compile(r"^/deployments/[^/]+$"),
)

DEPLOYMENTS_ALLOWED_WRITE_PATTERNS = (
    ("POST", re.compile(r"^/deployments$")),
    ("PATCH", re.compile(r"^/deployments/[^/]+$")),
    ("DELETE", re.compile(r"^/deployments/[^/]+$")),
    ("GET", re.compile(r"^/deployments/[^/]+$")),
    ("POST", re.compile(r"^/deployments/[^/]+/devices$")),
    ("PATCH", re.compile(r"^/deployments/[^/]+/devices/[^/]+$")),
    ("DELETE", re.compile(r"^/deployments/[^/]+/devices/[^/]+$")),
)

DEVICE_ALLOWED_ROUTES = (
    ("POST", "/upload-url"),
    ("GET", "/models"),
)


def _extract_api_key(event: Dict[str, Any]) -> Optional[str]:
    headers = event.get("headers", {}) or {}
    for header_name, header_value in headers.items():
        if header_name and header_name.lower() == "x-api-key":
            return header_value
    return None


def _lookup_device_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    return dynamodb.get_active_device_api_key(api_key)


def authenticate_api_key(event: Dict[str, Any]) -> Tuple[bool, str, Optional[str], AuthContext]:
    try:
        api_key = _extract_api_key(event)
        if not api_key:
            return False, "Missing API key. Include X-Api-Key header.", None, {}

        for key_name, key_value in CONFIGURED_KEYS.items():
            if api_key == key_value:
                if key_name == DEPLOYMENTS_API_KEY_ENV:
                    return True, "", "deployments", {"principal": "deployments"}
                if key_name in READ_ONLY_KEY_ENVS:
                    return True, "", "readonly", {"principal": "readonly"}
                return True, "", "admin", {"principal": "admin"}

        device_record = _lookup_device_api_key(api_key)
        if device_record:
            return True, "", "device", {"principal": "device", "device_record": device_record}

        return False, "Invalid API key", None, {}
    except Exception as exc:
        print(f"API key validation error: {exc}")
        return False, "Authentication error", None, {}


def validate_api_key(event: Dict[str, Any]) -> Tuple[bool, str]:
    is_valid, error_message, _, _ = authenticate_api_key(event)
    return is_valid, error_message


def authorize_request(
    event: Dict[str, Any],
    http_method: str,
    path: str,
) -> Tuple[bool, int, str, AuthContext]:
    if http_method == "OPTIONS":
        return True, 200, "", {}
    if http_method == "POST" and path == "/devices/register":
        return True, 200, "", {}

    is_valid, error_message, principal, auth_context = authenticate_api_key(event)
    if not is_valid:
        return False, 401, error_message, {}

    if principal == "admin":
        return True, 200, "", auth_context

    if principal == "device":
        if (http_method, path) in DEVICE_ALLOWED_ROUTES:
            return True, 200, "", auth_context
        return False, 403, f"API key is not allowed to call {http_method} {path}", auth_context

    if http_method == "GET":
        if path in READ_ONLY_ALLOWED_GET_PATHS:
            return True, 200, "", auth_context
        if any(pattern.match(path) for pattern in READ_ONLY_ALLOWED_GET_PATTERNS):
            return True, 200, "", auth_context
        if principal == "deployments" and any(
            method == "GET" and pattern.match(path)
            for method, pattern in DEPLOYMENTS_ALLOWED_WRITE_PATTERNS
        ):
            return True, 200, "", auth_context
    elif principal == "deployments" and any(
        method == http_method and pattern.match(path)
        for method, pattern in DEPLOYMENTS_ALLOWED_WRITE_PATTERNS
    ):
        return True, 200, "", auth_context

    return False, 403, f"API key is not allowed to call {http_method} {path}", auth_context
