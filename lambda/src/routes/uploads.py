from typing import Any, Dict

from s3 import OUTPUT_BUCKET, PRESIGNED_URL_EXPIRY, generate_presigned_put_url
from utils import _parse_request, json_response


def _validate_s3_key(s3_key: Any) -> str:
    if not isinstance(s3_key, str):
        raise ValueError("s3_key must be a string")
    normalized_key = s3_key.strip()
    if not normalized_key:
        raise ValueError("s3_key is required")
    if not normalized_key.startswith("v1/"):
        raise ValueError("s3_key must start with v1/")
    if ".." in normalized_key:
        raise ValueError("s3_key cannot contain '..'")
    return normalized_key


def _is_manifest_key(s3_key: str) -> bool:
    return s3_key == "v1/manifest.json"


def _validate_device_scope(s3_key: str, authenticated_device: Dict[str, Any]) -> None:
    if _is_manifest_key(s3_key):
        return

    allowed_devices = {str(authenticated_device.get("device_id") or "").strip()}
    allowed_devices.update(
        str(dot_id).strip()
        for dot_id in authenticated_device.get("dot_ids") or []
        if str(dot_id).strip()
    )
    allowed_devices.discard("")

    if len(s3_key.split("/", 2)) < 3:
        raise PermissionError("s3_key must include a device prefix and object path")

    key_device_id = s3_key.split("/", 2)[1]
    if key_device_id not in allowed_devices:
        raise PermissionError(f"s3_key is outside the authenticated device scope: {key_device_id}")


def handle_upload_url(
    event: Dict[str, Any],
    authenticated_device: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        if not authenticated_device:
            raise PermissionError("Authenticated device context is required")
        body = _parse_request(event)
        s3_key = _validate_s3_key(body.get("s3_key"))
        _validate_device_scope(s3_key, authenticated_device)
        upload_url = generate_presigned_put_url(s3_key, OUTPUT_BUCKET, PRESIGNED_URL_EXPIRY)
        if not upload_url:
            raise RuntimeError("Failed to generate upload URL")
        return json_response(
            200,
            {
                "upload_url": upload_url,
                "s3_key": s3_key,
                "expires_in": PRESIGNED_URL_EXPIRY,
            },
        )
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except PermissionError as exc:
        return json_response(403, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
