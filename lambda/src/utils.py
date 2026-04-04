import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs


DEFAULT_PAGE_LIMIT = 100
CSV_EXPORT_LIMIT = 5000
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


class DynamoDBEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, list) and all(isinstance(x, (int, float, Decimal)) for x in obj):
            return [float(x) if isinstance(x, Decimal) else x for x in obj]
        return super().default(obj)


def json_response(status_code: int, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    response_headers = dict(CORS_HEADERS)
    if headers:
        response_headers.update(headers)
    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps(payload, cls=DynamoDBEncoder),
    }


def cors_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return json_response(status_code, payload)


def _parse_request(event: Dict[str, Any]) -> Dict[str, Any]:
    if "body" not in event or event.get("body") in (None, ""):
        return {}
    if isinstance(event.get("body"), dict):
        return event["body"]
    body = json.loads(event["body"])
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body


def _get_query_params(event: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = dict(event.get("queryStringParameters") or {})
    raw_query = event.get("rawQueryString") or ""
    if raw_query:
        parsed = parse_qs(raw_query, keep_blank_values=False)
        for key, values in parsed.items():
            if not values:
                continue
            params[key] = values if len(values) > 1 else values[0]
    return params


def _get_query_list(params: Dict[str, Any], key: str) -> List[str]:
    value = params.get(key)
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: List[str] = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, str):
            result.extend(part.strip() for part in item.split(",") if part.strip())
        else:
            result.append(str(item))
    return result


def _resolve_device_filters(query_params: Dict[str, Any]) -> Optional[List[str]]:
    import dynamodb

    requested_device_ids = _get_query_list(query_params, "device_id")
    deployment_id = query_params.get("deployment_id")
    if deployment_id:
        deployment_device_ids = dynamodb.list_device_ids_for_deployment(str(deployment_id))
        if requested_device_ids:
            allowed = set(deployment_device_ids)
            requested_device_ids = [device_id for device_id in requested_device_ids if device_id in allowed]
        else:
            requested_device_ids = deployment_device_ids
        return requested_device_ids
    if requested_device_ids:
        return requested_device_ids
    return None


def _validate_interval_params(params: Dict[str, Any]) -> Tuple[int, str]:
    interval_length = _get_int_param(params, "interval_length")
    interval_unit = params.get("interval_unit")
    if interval_length in (None, 0) or interval_length < 0:
        raise ValueError("interval_length must be a positive integer")
    if interval_unit not in {"h", "d"}:
        raise ValueError("interval_unit must be one of: h, d")
    return interval_length, str(interval_unit)


def _get_bool_param(params: Dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _get_int_param(params: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
    value = params.get(key)
    if value in (None, ""):
        return default
    return int(value)


def _get_float_param(params: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    value = params.get(key)
    if value in (None, ""):
        return default
    return float(value)


def _make_offset_naive(timestamp: str) -> str:
    parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat()


def _clean_timestamps(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for item in items:
        if "timestamp" in item:
            item["timestamp"] = _make_offset_naive(item["timestamp"])
    return items


def _common_post_handler(
    event: Dict[str, Any],
    data_type: str,
    store_function: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        import dynamodb

        body = _parse_request(event)
        device_id = body.get("device_id")
        if device_id:
            try:
                dynamodb.store_device_if_not_exists(device_id)
            except Exception as exc:
                print(f"Warning: failed to store device_id {device_id}: {exc}")
        return store_function(body)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        print(f"Error in {data_type} POST handler: {exc}")
        return json_response(500, {"error": str(exc)})


def _common_get_handler(
    event: Dict[str, Any],
    data_type: str,
    process_results: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    try:
        import dynamodb

        query_params = _get_query_params(event)
        result = dynamodb.query_data(
            data_type,
            device_id=query_params.get("device_id"),
            model_id=query_params.get("model_id"),
            start_time=query_params.get("start_time"),
            end_time=query_params.get("end_time"),
            limit=_get_int_param(query_params, "limit", DEFAULT_PAGE_LIMIT) or DEFAULT_PAGE_LIMIT,
            next_token=query_params.get("next_token"),
            sort_by=query_params.get("sort_by"),
            sort_desc=_get_bool_param(query_params, "sort_desc"),
        )
        if "items" in result:
            result["items"] = _clean_timestamps(result["items"])
        if process_results:
            result = process_results(result)
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        print(f"Error in {data_type} GET handler: {exc}")
        return json_response(500, {"error": str(exc)})
