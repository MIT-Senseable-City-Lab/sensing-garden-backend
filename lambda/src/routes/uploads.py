from typing import Any, Dict

import activity
from s3 import OUTPUT_BUCKET, PRESIGNED_URL_EXPIRY, generate_presigned_put_url
from utils import _parse_request, json_response


# Hourly batch archives upload here; their members are v1 keys but the container
# itself lives under v2/archives/<device>/<timestamp>.tar.
ARCHIVE_PREFIX = "v2/archives/"


def _validate_s3_key(s3_key: Any) -> str:
    if not isinstance(s3_key, str):
        raise ValueError("s3_key must be a string")
    normalized_key = s3_key.strip()
    if not normalized_key:
        raise ValueError("s3_key is required")
    if not (normalized_key.startswith("v1/") or normalized_key.startswith(ARCHIVE_PREFIX)):
        raise ValueError("s3_key must start with v1/ or v2/archives/")
    if ".." in normalized_key:
        raise ValueError("s3_key cannot contain '..'")
    return normalized_key


def _is_manifest_key(s3_key: str) -> bool:
    return s3_key == "v1/manifest.json"


def _key_device_id(s3_key: str) -> str:
    """The device id is the segment after the namespace prefix:
    v1/<device>/...  or  v2/archives/<device>/..."""
    if s3_key.startswith(ARCHIVE_PREFIX):
        rest = s3_key[len(ARCHIVE_PREFIX):].split("/", 1)
        if len(rest) < 2 or not rest[0]:
            raise PermissionError("archive s3_key must include a device prefix and object path")
        return rest[0]
    parts = s3_key.split("/", 2)
    if len(parts) < 3:
        raise PermissionError("s3_key must include a device prefix and object path")
    return parts[1]


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

    key_device_id = _key_device_id(s3_key)
    if key_device_id not in allowed_devices:
        raise PermissionError(f"s3_key is outside the authenticated device scope: {key_device_id}")


def _record_upload_url(device_id: str, s3_key: str, status_code: int) -> None:
    activity.record_activity_event(
        activity.ActivityEvent(
            timestamp=activity.utc_now(),
            source=activity.ActivitySource.BACKEND,
            event_type=activity.ActivityEventType.UPLOAD_URL_REQUESTED,
            device_id=device_id or None,
            method="POST",
            path="/upload-url",
            status_code=status_code,
            s3_bucket=OUTPUT_BUCKET,
            s3_key=s3_key or None,
            message=f"Upload URL requested -> {status_code}",
        )
    )


def handle_upload_url(
    event: Dict[str, Any],
    authenticated_device: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    device_id = str((authenticated_device or {}).get("device_id") or "")
    s3_key = ""
    try:
        if not authenticated_device:
            raise PermissionError("Authenticated device context is required")
        body = _parse_request(event)
        s3_key = _validate_s3_key(body.get("s3_key"))
        _validate_device_scope(s3_key, authenticated_device)
        upload_url = generate_presigned_put_url(s3_key, OUTPUT_BUCKET, PRESIGNED_URL_EXPIRY)
        if not upload_url:
            raise RuntimeError("Failed to generate upload URL")
        _record_upload_url(device_id, s3_key, 200)
        return json_response(
            200,
            {
                "upload_url": upload_url,
                "s3_key": s3_key,
                "expires_in": PRESIGNED_URL_EXPIRY,
            },
        )
    except ValueError as exc:
        _record_upload_url(device_id, s3_key, 400)
        return json_response(400, {"error": str(exc)})
    except PermissionError as exc:
        _record_upload_url(device_id, s3_key, 403)
        return json_response(403, {"error": str(exc)})
    except Exception as exc:
        _record_upload_url(device_id, s3_key, 500)
        return json_response(500, {"error": str(exc)})

def handle_batch_upload_url(
    event: Dict[str, Any],
    authenticated_device: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    device_id = str((authenticated_device or {}).get("device_id") or "")
    try:
        if not authenticated_device:
            raise PermissionError("Authenticated device context is required")
        body = _parse_request(event)
        raw_keys = body.get("s3_keys")
        if not isinstance(raw_keys, list) or not raw_keys:
            raise ValueError("s3_keys must be a non-empty list")
        if len(raw_keys) > 200:
            raise ValueError("s3_keys must contain 200 or fewer keys per request")

        results = []
        for s3_key in raw_keys:
            validated_key = _validate_s3_key(s3_key)
            _validate_device_scope(validated_key, authenticated_device)
            upload_url = generate_presigned_put_url(validated_key, OUTPUT_BUCKET, PRESIGNED_URL_EXPIRY)
            if not upload_url:
                raise RuntimeError(f"Failed to generate upload URL for {validated_key}")
            results.append({"s3_key": validated_key, "upload_url": upload_url})

        _record_upload_url(device_id, f"batch:{len(raw_keys)}", 200)
        return json_response(
            200,
            {
                "upload_urls": results,
                "expires_in": PRESIGNED_URL_EXPIRY,
            },
        )
    except ValueError as exc:
        _record_upload_url(device_id, "batch", 400)
        return json_response(400, {"error": str(exc)})
    except PermissionError as exc:
        _record_upload_url(device_id, "batch", 403)
        return json_response(403, {"error": str(exc)})
    except Exception as exc:
        _record_upload_url(device_id, "batch", 500)
        return json_response(500, {"error": str(exc)})
