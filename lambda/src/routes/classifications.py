from typing import Any, Dict, Optional

import dynamodb
from s3 import _add_presigned_urls
from utils import (
    DEFAULT_PAGE_LIMIT,
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


def _validate_taxonomy_level(taxonomy_level: Optional[str]) -> None:
    if taxonomy_level and taxonomy_level not in {"family", "genus", "species"}:
        raise ValueError("taxonomy_level must be one of: family, genus, species")


def handle_get_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        taxonomy_level = params.get("taxonomy_level")
        _validate_taxonomy_level(taxonomy_level)
        result = dynamodb.count_classifications(
            device_ids=_resolve_device_filters(params),
            model_id=params.get("model_id"),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            min_confidence=_get_float_param(params, "min_confidence"),
            taxonomy_level=taxonomy_level,
            selected_taxa=_get_query_list(params, "selected_taxa"),
        )
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        taxonomy_level = params.get("taxonomy_level")
        _validate_taxonomy_level(taxonomy_level)
        result = dynamodb.list_classifications(
            device_ids=_resolve_device_filters(params),
            model_id=params.get("model_id"),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            min_confidence=_get_float_param(params, "min_confidence"),
            taxonomy_level=taxonomy_level,
            selected_taxa=_get_query_list(params, "selected_taxa"),
            limit=_get_int_param(params, "limit", DEFAULT_PAGE_LIMIT) or DEFAULT_PAGE_LIMIT,
            next_token=params.get("next_token"),
            sort_by=params.get("sort_by"),
            sort_desc=_get_bool_param(params, "sort_desc"),
        )
        result["items"] = _clean_timestamps(result.get("items", []))
        result = _add_presigned_urls(result)
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get_taxa_count(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        taxonomy_level = params.get("taxonomy_level")
        _validate_taxonomy_level(taxonomy_level)
        if not taxonomy_level:
            raise ValueError("taxonomy_level is required")
        result = dynamodb.get_classification_taxa_count(
            device_ids=_resolve_device_filters(params),
            model_id=params.get("model_id"),
            start_time=params.get("start_time"),
            end_time=params.get("end_time"),
            min_confidence=_get_float_param(params, "min_confidence"),
            taxonomy_level=taxonomy_level,
            selected_taxa=_get_query_list(params, "selected_taxa"),
            sort_desc=_get_bool_param(params, "sort_desc"),
        )
        return json_response(200, result)
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:
        return json_response(500, {"error": str(exc)})


def handle_get_time_series(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        params = _get_query_params(event)
        taxonomy_level = params.get("taxonomy_level")
        _validate_taxonomy_level(taxonomy_level)
        interval_length, interval_unit = _validate_interval_params(params)
        result = dynamodb.get_classification_time_series(
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
