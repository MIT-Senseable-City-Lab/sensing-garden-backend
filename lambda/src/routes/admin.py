from typing import Any, Dict

import activity
import dynamodb
from utils import _get_query_params, json_response


def handle_orphaned_devices(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = dynamodb.find_orphaned_device_ids()
        return json_response(200, result)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def _activity_limit(value: Any) -> int:
    limit = int(value or 100)
    return max(1, min(limit, 200))


def handle_activity(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        items = activity.list_activity_events(
            str(params.get("source", "")),
            str(params.get("device_id", "")),
            str(params.get("q", "")),
            _activity_limit(params.get("limit")),
        )
        return json_response(200, {"items": items, "count": len(items)})
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
