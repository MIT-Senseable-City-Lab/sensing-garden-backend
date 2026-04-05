from typing import Any, Dict

import dynamodb
from utils import _clean_timestamps, _get_query_params, json_response


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        device_id = params.get("device_id")
        if device_id:
            result = dynamodb.get_heartbeats_for_device(str(device_id))
        else:
            result = dynamodb.get_latest_heartbeats()
        result["items"] = _clean_timestamps(result.get("items", []))
        return json_response(200, result)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
