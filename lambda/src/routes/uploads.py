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


def handle_upload_url(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        s3_key = _validate_s3_key(body.get("s3_key"))
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
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
