from typing import Any, Dict

import dynamodb
from s3 import _add_presigned_urls
from utils import _common_get_handler, _get_query_params, json_response


def handle_get_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.count_data(
            "detection",
            params.get("device_id"),
            params.get("model_id"),
            params.get("start_time"),
            params.get("end_time"),
        )
        return json_response(200, result)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    return _common_get_handler(event, "detection", _add_presigned_urls)
