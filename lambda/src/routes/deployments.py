import base64
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import dynamodb
from s3 import IMAGES_BUCKET, _add_presigned_urls, delete_s3_object, s3
from utils import DEFAULT_PAGE_LIMIT, _get_bool_param, _get_int_param, _get_query_params, _parse_request, json_response


def _normalize_location(location: Dict[str, Any]) -> Dict[str, Decimal]:
    normalized = {
        "lat": Decimal(str(location["lat"])),
        "long": Decimal(str(location["long"])),
    }
    if "alt" in location:
        normalized["alt"] = Decimal(str(location["alt"]))
    return normalized


def _normalize_deployment_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = item.copy()
    if "image_key" in normalized and "image_bucket" in normalized:
        result = _add_presigned_urls({"items": [normalized]})
        return result["items"][0]
    return normalized


def _upload_deployment_image(body_image: str, deployment_id: str, timestamp: str) -> str:
    s3_key = f"deployment/{deployment_id}/{timestamp}.jpg"
    s3.put_object(
        Bucket=IMAGES_BUCKET,
        Key=s3_key,
        Body=base64.b64decode(body_image),
        ContentType="image/jpeg",
    )
    return s3_key


def _build_deployment_data(body: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "deployment_id": body.get("deployment_id") or str(uuid.uuid4()),
        "name": body["name"],
        "description": body["description"],
        "start_time": body.get("start_time", datetime.now(timezone.utc).isoformat()),
    }
    for optional_field in ("end_time", "model_id", "location_name"):
        if optional_field in body and body[optional_field] is not None:
            data[optional_field] = body[optional_field]
    if "location" in body:
        data["location"] = _normalize_location(body["location"])
    return data


def _attach_deployment_image(data: Dict[str, Any], body: Dict[str, Any]) -> Optional[str]:
    if "image" not in body:
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    uploaded_image_key = _upload_deployment_image(body["image"], data["deployment_id"], timestamp)
    data["image_key"] = uploaded_image_key
    data["image_bucket"] = IMAGES_BUCKET
    return uploaded_image_key


def _cleanup_uploaded_image(uploaded_image_key: Optional[str]) -> None:
    if not uploaded_image_key:
        return
    try:
        delete_s3_object(uploaded_image_key)
    except Exception as exc:
        print(f"Failed to clean up uploaded deployment image {uploaded_image_key}: {exc}")


def _store_deployment(body: Dict[str, Any]) -> Dict[str, Any]:
    data = _build_deployment_data(body)
    uploaded_image_key = _attach_deployment_image(data, body)

    try:
        response = dynamodb.store_deployment_data(data)
    except Exception:
        _cleanup_uploaded_image(uploaded_image_key)
        raise

    if uploaded_image_key and response.get("statusCode") != 200:
        _cleanup_uploaded_image(uploaded_image_key)
    return response


def _build_deployment_device_payload(body: Dict[str, Any], deployment_id: str, device_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "deployment_id": deployment_id,
        "device_id": device_id or body.get("device_id"),
    }
    if not payload["device_id"]:
        raise ValueError("device_id is required")
    if not dynamodb.device_exists(payload["device_id"]):
        raise ValueError(f"device_id {payload['device_id']} was not found")
    if "name" in body:
        payload["name"] = body["name"]
    if "location" in body:
        payload["location"] = _normalize_location(body["location"])
    return payload


def handle_get_list(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.list_deployments(
            limit=_get_int_param(params, "limit", DEFAULT_PAGE_LIMIT) or DEFAULT_PAGE_LIMIT,
            next_token=params.get("next_token"),
            sort_by=params.get("sort_by"),
            sort_desc=_get_bool_param(params, "sort_desc"),
        )
        result["deployments"] = [_normalize_deployment_item(item) for item in result.pop("items", [])]
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get(event: Dict[str, Any], deployment_id: str) -> Dict[str, Any]:
    try:
        deployment = dynamodb.get_deployment(deployment_id)
        if not deployment:
            return json_response(404, {"error": f"Deployment {deployment_id} not found"})
        devices = dynamodb.list_deployment_devices(deployment_id)
        return json_response(
            200,
            {
                "deployment": _normalize_deployment_item(deployment),
                "devices": devices,
            },
        )
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_post(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        for field in ("name", "description"):
            if not body.get(field):
                raise ValueError(f"{field} is required")
        return _store_deployment(body)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_patch(event: Dict[str, Any], deployment_id: str) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        if not body:
            raise ValueError("Request body is required")

        updates: Dict[str, Any] = {}
        for optional_field in ("name", "description", "start_time", "end_time", "model_id", "location_name"):
            if optional_field in body:
                updates[optional_field] = body[optional_field]
        if "location" in body:
            updates["location"] = _normalize_location(body["location"])
        if "image" in body:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
            updates["image_key"] = _upload_deployment_image(body["image"], deployment_id, timestamp)
            updates["image_bucket"] = IMAGES_BUCKET
        if not updates:
            raise ValueError("No updatable fields provided")
        return dynamodb.update_deployment_data(deployment_id, updates)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_delete(event: Dict[str, Any], deployment_id: str) -> Dict[str, Any]:
    try:
        return dynamodb.delete_deployment(deployment_id)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_create_device_assignment(event: Dict[str, Any], deployment_id: str) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        payload = _build_deployment_device_payload(body, deployment_id)
        return dynamodb.store_deployment_device_connection_data(payload)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_update_device_assignment(event: Dict[str, Any], deployment_id: str, device_id: str) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        updates = _build_deployment_device_payload(body, deployment_id, device_id)
        updates.pop("deployment_id", None)
        updates.pop("device_id", None)
        if not updates:
            raise ValueError("No updatable fields provided")
        return dynamodb.update_deployment_device_connection(deployment_id, device_id, updates)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_remove_device_assignment(event: Dict[str, Any], deployment_id: str, device_id: str) -> Dict[str, Any]:
    try:
        return dynamodb.delete_deployment_device_connection(deployment_id, device_id)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
