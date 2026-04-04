from typing import Any, Dict

import dynamodb
from utils import (
    _common_get_handler,
    _get_query_params,
    _resolve_device_filters,
    _validate_interval_params,
    json_response,
)


def handle_get_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.count_data(
            "environmental_reading",
            params.get("device_id"),
            None,
            params.get("start_time"),
            params.get("end_time"),
        )
        return json_response(200, result)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    return _common_get_handler(event, "environmental_reading")


def handle_get_time_series(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        interval_length, interval_unit = _validate_interval_params(params)
        result = dynamodb.get_environment_time_series(
            device_ids=_resolve_device_filters(params),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            interval_length=interval_length,
            interval_unit=interval_unit,
        )
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
