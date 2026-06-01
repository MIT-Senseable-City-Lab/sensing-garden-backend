from typing import Any, Dict

import dynamodb
from s3 import OUTPUT_BUCKET, generate_presigned_url
from utils import (
    DEFAULT_PAGE_LIMIT,
    HeatmapPeriod,
    TaxonomyLevel,
    _clean_timestamps,
    _get_bool_param,
    _get_float_param,
    _get_int_param,
    _get_query_list,
    _get_query_params,
    _resolve_device_filters,
    _validate_interval_params,
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


def _validate_taxonomy_level(taxonomy_level: object) -> None:
    TaxonomyLevel.parse_optional(str(taxonomy_level) if taxonomy_level is not None else None)


def handle_get_time_series(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        taxonomy_level = params.get("taxonomy_level")
        _validate_taxonomy_level(taxonomy_level)
        interval_length, interval_unit = _validate_interval_params(params)
        result = dynamodb.get_track_time_series(
            device_ids=_resolve_device_filters(params),
            model_id=params.get("model_id"),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            min_confidence=_get_float_param(params, "min_confidence"),
            taxonomy_level=taxonomy_level,
            selected_taxa=_get_query_list(params, "selected_taxa"),
            interval_length=interval_length,
            interval_unit=interval_unit,
        )
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get_heatmap(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        taxonomy_level = params.get("taxonomy_level")
        _validate_taxonomy_level(taxonomy_level)
        period = HeatmapPeriod.parse(params.get("period"))
        result = dynamodb.get_track_heatmap(
            device_ids=_resolve_device_filters(params),
            model_id=params.get("model_id"),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            min_confidence=_get_float_param(params, "min_confidence"),
            taxonomy_level=taxonomy_level,
            selected_taxa=_get_query_list(params, "selected_taxa"),
            period=period,
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
