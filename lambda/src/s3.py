import os
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config


s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

IMAGES_BUCKET = os.environ.get("IMAGES_BUCKET", "scl-sensing-garden-images")
VIDEOS_BUCKET = os.environ.get("VIDEOS_BUCKET", "scl-sensing-garden-videos")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "scl-sensing-garden")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "scl-sensing-garden-models")
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


def generate_presigned_put_url(
    s3_key: str,
    bucket: str = OUTPUT_BUCKET,
    expiration: int = PRESIGNED_URL_EXPIRY,
) -> Optional[str]:
    try:
        return s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expiration,
        )
    except Exception as exc:
        print(f"Error generating presigned PUT URL: {exc}")
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


def list_model_bundles() -> list[Dict[str, Any]]:
    """List model bundles from S3 by scanning for */model.hef keys."""
    paginator = s3.get_paginator("list_objects_v2")
    bundles: Dict[str, Dict[str, Any]] = {}
    for page in paginator.paginate(Bucket=MODELS_BUCKET):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            parts = key.split("/", 1)
            if len(parts) != 2:
                continue
            bundle_name, filename = parts
            if bundle_name not in bundles:
                bundles[bundle_name] = {"model_id": bundle_name, "files": []}
            bundles[bundle_name]["files"].append(filename)
            if filename == "model.hef":
                bundles[bundle_name]["size_bytes"] = obj.get("Size", 0)
                bundles[bundle_name]["last_modified"] = obj["LastModified"].isoformat() if obj.get("LastModified") else ""
    return sorted(bundles.values(), key=lambda b: b.get("model_id", ""))
