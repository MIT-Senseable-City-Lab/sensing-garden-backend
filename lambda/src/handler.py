import re
from typing import Any, Callable, Dict, Pattern, Tuple

import dynamodb
from auth import AuthContext, authorize_request
from routes import (
    admin,
    classifications,
    deployments,
    detections,
    devices,
    environment,
    export,
    heartbeats,
    models,
    registration,
    tracks,
    uploads,
    videos,
)
from utils import CORS_HEADERS, cors_response

RouteHandler = Callable[..., Dict[str, Any]]
ParameterizedRoute = Tuple[str, Pattern[str], RouteHandler]


ROUTES: Dict[Tuple[str, str], RouteHandler] = {
    ("GET", "/classifications"): classifications.handle_get,
    ("GET", "/classifications/count"): classifications.handle_get_count,
    ("GET", "/classifications/taxa_count"): classifications.handle_get_taxa_count,
    ("GET", "/classifications/time_series"): classifications.handle_get_time_series,
    ("GET", "/detections"): detections.handle_get,
    ("GET", "/detections/count"): detections.handle_get_count,
    ("GET", "/devices"): devices.handle_get,
    ("DELETE", "/devices"): devices.handle_delete,
    ("POST", "/devices/register"): registration.handle_register,
    ("GET", "/models"): models.handle_get,
    ("GET", "/models/count"): models.handle_get_count,
    ("POST", "/upload-url"): uploads.handle_upload_url,
    ("GET", "/videos"): videos.handle_get,
    ("GET", "/videos/count"): videos.handle_get_count,
    ("GET", "/environment"): environment.handle_get,
    ("GET", "/environment/count"): environment.handle_get_count,
    ("GET", "/environment/time_series"): environment.handle_get_time_series,
    ("GET", "/tracks"): tracks.handle_get,
    ("GET", "/tracks/count"): tracks.handle_get_count,
    ("GET", "/heartbeats"): heartbeats.handle_get,
    ("GET", "/export"): export.handle_export,
    ("GET", "/admin/orphaned-devices"): admin.handle_orphaned_devices,
    ("GET", "/admin/activity"): admin.handle_activity,
    ("GET", "/deployments"): deployments.handle_get_list,
    ("POST", "/deployments"): deployments.handle_post,
}

PARAMETERIZED_ROUTES: Tuple[ParameterizedRoute, ...] = (
    ("GET", re.compile(r"^/tracks/(?P<track_id>[^/]+)$"), tracks.handle_get_single),
    ("GET", re.compile(r"^/deployments/(?P<deployment_id>[^/]+)$"), deployments.handle_get),
    ("PATCH", re.compile(r"^/deployments/(?P<deployment_id>[^/]+)$"), deployments.handle_patch),
    ("DELETE", re.compile(r"^/deployments/(?P<deployment_id>[^/]+)$"), deployments.handle_delete),
    ("POST", re.compile(r"^/deployments/(?P<deployment_id>[^/]+)/devices$"), deployments.handle_create_device_assignment),
    (
        "PATCH",
        re.compile(r"^/deployments/(?P<deployment_id>[^/]+)/devices/(?P<device_id>[^/]+)$"),
        deployments.handle_update_device_assignment,
    ),
    (
        "DELETE",
        re.compile(r"^/deployments/(?P<deployment_id>[^/]+)/devices/(?P<device_id>[^/]+)$"),
        deployments.handle_remove_device_assignment,
    ),
)


def _resolve_http_request(event: Dict[str, Any]) -> Dict[str, str]:
    http = event.get("requestContext", {}).get("http", {})
    return {
        "method": http.get("method", ""),
        "path": http.get("path", ""),
    }


def _invoke_route(
    route_handler: RouteHandler,
    event: Dict[str, Any],
    auth_context: AuthContext,
    **path_params: str,
) -> Dict[str, Any]:
    if route_handler is uploads.handle_upload_url:
        return route_handler(event, authenticated_device=auth_context.get("device_record"))
    if path_params:
        return route_handler(event, **path_params)
    return route_handler(event)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        request = _resolve_http_request(event)
        method = request["method"]
        path = request["path"]

        if method == "OPTIONS":
            return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

        is_authorized, status_code, auth_message, auth_context = authorize_request(event, method, path)
        if not is_authorized:
            return cors_response(status_code, {"error": auth_message})

        route_handler = ROUTES.get((method, path))
        if route_handler:
            return _invoke_route(route_handler, event, auth_context)

        for route_method, pattern, route_handler in PARAMETERIZED_ROUTES:
            if route_method != method:
                continue
            match = pattern.match(path)
            if match:
                return _invoke_route(route_handler, event, auth_context, **match.groupdict())

        return cors_response(404, {"error": f"No handler for {method} {path}"})
    except Exception as exc:
        return cors_response(500, {"error": str(exc)})


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return lambda_handler(event, context)
