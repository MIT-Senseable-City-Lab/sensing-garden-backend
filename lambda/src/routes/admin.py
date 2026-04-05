from typing import Any, Dict

import dynamodb
from utils import json_response


def handle_orphaned_devices(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = dynamodb.find_orphaned_device_ids()
        return json_response(200, result)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
