from datetime import datetime, timezone
from typing import Any, Dict

import dynamodb
from utils import _common_get_handler, _common_post_handler, _get_query_params, _parse_request, json_response


def _store_model(body: Dict[str, Any]) -> Dict[str, Any]:
    for field in ("model_id", "name", "description", "version"):
        if not body.get(field):
            raise ValueError(f"{field} is required")
    data = {
        "id": body["model_id"],
        "timestamp": body.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "name": body["name"],
        "description": body["description"],
        "version": body["version"],
    }
    if "metadata" in body:
        data["metadata"] = body["metadata"]
    return dynamodb.store_model_data(data)


def handle_get_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.count_data(
            "model",
            params.get("device_id"),
            params.get("model_id"),
            params.get("start_time"),
            params.get("end_time"),
        )
        return json_response(200, result)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    return _common_get_handler(event, "model")


def handle_post(event: Dict[str, Any]) -> Dict[str, Any]:
    return _common_post_handler(event, "model", _store_model)


def handle_delete(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        model_id = body.get("model_id")
        if not model_id:
            raise ValueError("model_id is required in body")
        return dynamodb.delete_model(model_id)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
