"""Presigned multipart upload endpoints for large device uploads (e.g. hourly
batch tars). The device has no AWS credentials, so the backend drives the
multipart lifecycle: create the upload, hand back a presigned URL per part, then
complete (or abort). Keys are validated and device-scoped exactly like /upload-url
(so v1/ and v2/archives/<device>/ are accepted).
"""
from typing import Any, Dict

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from routes.uploads import _validate_device_scope, _validate_s3_key
from s3 import OUTPUT_BUCKET, PRESIGNED_URL_EXPIRY
from utils import _parse_request, json_response

# S3 error codes that mean the multipart upload no longer exists; surfaced as 404
# so the device drops its stale upload id and restarts.
_GONE_CODES = {"NoSuchUpload", "NoSuchKey"}


def _client():
    # SigV4 so presigned upload_part URLs validate everywhere (matches s3.py).
    return boto3.client("s3", config=Config(signature_version="s3v4"))


def _scoped_key(event: Dict[str, Any], authenticated_device: Dict[str, Any] | None):
    if not authenticated_device:
        raise PermissionError("Authenticated device context is required")
    body = _parse_request(event)
    s3_key = _validate_s3_key(body.get("s3_key"))
    _validate_device_scope(s3_key, authenticated_device)
    return body, s3_key


def _require(body: Dict[str, Any], name: str) -> Any:
    value = body.get(name)
    if value in (None, ""):
        raise ValueError(f"{name} is required")
    return value


def _gone_or_500(exc: ClientError) -> Dict[str, Any]:
    if exc.response.get("Error", {}).get("Code") in _GONE_CODES:
        return json_response(404, {"error": "multipart upload gone"})
    return json_response(500, {"error": str(exc)})


def handle_multipart_create(event, authenticated_device=None):
    try:
        _, s3_key = _scoped_key(event, authenticated_device)
        resp = _client().create_multipart_upload(Bucket=OUTPUT_BUCKET, Key=s3_key)
        return json_response(200, {"upload_id": resp["UploadId"], "s3_key": s3_key})
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except PermissionError as exc:
        return json_response(403, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return json_response(500, {"error": str(exc)})


def handle_multipart_part_url(event, authenticated_device=None):
    try:
        body, s3_key = _scoped_key(event, authenticated_device)
        upload_id = _require(body, "upload_id")
        try:
            part_number = int(_require(body, "part_number"))
        except (TypeError, ValueError):
            raise ValueError("part_number must be an integer")
        url = _client().generate_presigned_url(
            "upload_part",
            Params={"Bucket": OUTPUT_BUCKET, "Key": s3_key, "UploadId": upload_id, "PartNumber": part_number},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
        return json_response(200, {"upload_url": url})
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except PermissionError as exc:
        return json_response(403, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return json_response(500, {"error": str(exc)})


def handle_multipart_complete(event, authenticated_device=None):
    try:
        body, s3_key = _scoped_key(event, authenticated_device)
        upload_id = _require(body, "upload_id")
        raw_parts = body.get("parts") or []
        if not raw_parts:
            raise ValueError("parts is required")
        parts = [
            {"ETag": p["etag"], "PartNumber": int(p["part_number"])}
            for p in sorted(raw_parts, key=lambda p: int(p["part_number"]))
        ]
        _client().complete_multipart_upload(
            Bucket=OUTPUT_BUCKET, Key=s3_key, UploadId=upload_id, MultipartUpload={"Parts": parts}
        )
        return json_response(200, {"s3_key": s3_key})
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except (KeyError, TypeError) as exc:
        return json_response(400, {"error": f"malformed parts: {exc}"})
    except PermissionError as exc:
        return json_response(403, {"error": str(exc)})
    except ClientError as exc:
        return _gone_or_500(exc)
    except Exception as exc:  # noqa: BLE001
        return json_response(500, {"error": str(exc)})


def handle_multipart_abort(event, authenticated_device=None):
    try:
        body, s3_key = _scoped_key(event, authenticated_device)
        upload_id = _require(body, "upload_id")
        _client().abort_multipart_upload(Bucket=OUTPUT_BUCKET, Key=s3_key, UploadId=upload_id)
        return json_response(200, {"s3_key": s3_key})
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except PermissionError as exc:
        return json_response(403, {"error": str(exc)})
    except ClientError as exc:
        return _gone_or_500(exc)
    except Exception as exc:  # noqa: BLE001
        return json_response(500, {"error": str(exc)})
