from typing import Any, Dict

import s3
from utils import json_response


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        bundles = s3.list_model_bundles()
        return json_response(200, {"items": bundles, "count": len(bundles)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        bundles = s3.list_model_bundles()
        return json_response(200, {"count": len(bundles)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
