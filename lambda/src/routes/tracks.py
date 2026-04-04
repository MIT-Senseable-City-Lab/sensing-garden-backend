from typing import Any, Dict

import dynamodb
from s3 import OUTPUT_BUCKET, generate_presigned_url
from utils import (
    DEFAULT_PAGE_LIMIT,
    _clean_timestamps,
    _get_bool_param,
    _get_int_param,
    _get_query_params,
    _resolve_device_filters,
    json_response,
)


def _add_composite_url(item: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(item)
    composite_key = normalized.get("composite_key")
    if composite_key:
        normalized["composite_url"] = generate_presigned_url(str(composite_key), OUTPUT_BUCKET)
    return normalized


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.list_tracks(
            device_ids=_resolve_device_filters(params),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            limit=_get_int_param(params, "limit", DEFAULT_PAGE_LIMIT) or DEFAULT_PAGE_LIMIT,
            next_token=params.get("next_token"),
            sort_by=params.get("sort_by"),
            sort_desc=_get_bool_param(params, "sort_desc"),
        )
        result["items"] = [_add_composite_url(item) for item in _clean_timestamps(result.get("items", []))]
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        result = dynamodb.count_tracks(
            device_ids=_resolve_device_filters(params),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
        )
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get_single(event: Dict[str, Any], track_id: str) -> Dict[str, Any]:
    try:
        track = dynamodb.get_track(track_id)
        if not track:
            return json_response(404, {"error": f"Track {track_id} not found"})
        track = _add_composite_url(track)
        _clean_timestamps([track])
        return json_response(200, {"track": track})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
