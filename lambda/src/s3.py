import os
from typing import Any, Dict, Optional

import boto3


s3 = boto3.client("s3")

IMAGES_BUCKET = os.environ.get("IMAGES_BUCKET", "scl-sensing-garden-images")
VIDEOS_BUCKET = os.environ.get("VIDEOS_BUCKET", "scl-sensing-garden-videos")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "scl-sensing-garden")
PRESIGNED_URL_EXPIRY = 3600


def generate_presigned_url(
    s3_key: str,
    bucket: Optional[str] = None,
    expiration: int = PRESIGNED_URL_EXPIRY,
) -> Optional[str]:
    try:
        target_bucket = bucket or IMAGES_BUCKET
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": target_bucket, "Key": s3_key},
            ExpiresIn=expiration,
        )
    except Exception as exc:
        print(f"Error generating presigned URL: {exc}")
        return None


def _add_presigned_urls(result: Dict[str, Any]) -> Dict[str, Any]:
    for item in result.get("items", []):
        if "image_key" in item and "image_bucket" in item:
            item["image_url"] = generate_presigned_url(item["image_key"], item["image_bucket"])
        if "video_key" in item and "video_bucket" in item:
            item["video_url"] = generate_presigned_url(item["video_key"], item["video_bucket"])
    return result

def delete_s3_object(s3_key: str, bucket: str = IMAGES_BUCKET) -> None:
    s3.delete_object(Bucket=bucket, Key=s3_key)
