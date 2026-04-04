from typing import Any, Dict

import dynamodb
from utils import DEFAULT_PAGE_LIMIT, _get_bool_param, _get_int_param, _get_query_params, _parse_request, json_response


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.get_devices(
            device_id=params.get("device_id"),
            created=params.get("created"),
            limit=_get_int_param(params, "limit", DEFAULT_PAGE_LIMIT) or DEFAULT_PAGE_LIMIT,
            next_token=params.get("next_token"),
            sort_by=params.get("sort_by"),
            sort_desc=_get_bool_param(params, "sort_desc"),
        )
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_delete(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = _parse_request(event)
        device_id = body.get("device_id")
        if not device_id:
            raise ValueError("device_id is required in body")
        cascade = body.get("cascade", True)
        return dynamodb.delete_device(device_id, cascade=cascade)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
