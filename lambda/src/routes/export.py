from datetime import datetime
from typing import Any, Dict

import csv_utils
import dynamodb
from utils import CSV_EXPORT_LIMIT, _get_bool_param, _get_query_params, json_response


TABLE_MAPPING = {
    "detections": "detection",
    "classifications": "classification",
    "models": "model",
    "videos": "video",
    "environment": "environmental_reading",
    "devices": "device",
}
MAX_PAGINATION_PAGES = 50


def handle_export(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        query_params = _get_query_params(event)
        table_param = query_params.get("table")
        if not table_param:
            return json_response(400, {"error": "table parameter is required"})
        if table_param not in TABLE_MAPPING:
            valid_tables = ", ".join(TABLE_MAPPING.keys())
            return json_response(400, {"error": f"Invalid table parameter. Valid options are: {valid_tables}"})

        start_time = query_params.get("start_time")
        end_time = query_params.get("end_time")
        if not start_time or not end_time:
            return json_response(400, {"error": "Both start_time and end_time parameters are required"})

        try:
            datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        except ValueError as exc:
            return json_response(
                400,
                {"error": f"Invalid date format. Use ISO 8601 format (e.g., 2023-01-01T00:00:00Z): {exc}"},
            )

        data_type = TABLE_MAPPING[table_param]
        all_items = []
        next_token = None

        page_count = 0
        while page_count < MAX_PAGINATION_PAGES:
            if data_type == "device":
                result = dynamodb.get_devices(
                    device_id=query_params.get("device_id"),
                    created=query_params.get("created"),
                    limit=CSV_EXPORT_LIMIT,
                    next_token=next_token,
                    sort_by=query_params.get("sort_by"),
                    sort_desc=_get_bool_param(query_params, "sort_desc"),
                )
            else:
                result = dynamodb.query_data(
                    data_type,
                    device_id=query_params.get("device_id"),
                    model_id=query_params.get("model_id"),
                    start_time=start_time,
                    end_time=end_time,
                    limit=CSV_EXPORT_LIMIT,
                    next_token=next_token,
                    sort_by=query_params.get("sort_by"),
                    sort_desc=_get_bool_param(query_params, "sort_desc"),
                )

            all_items.extend(result.get("items", []))
            next_token = result.get("next_token")
            if not next_token:
                break
            page_count += 1

        if not all_items:
            filename = f'{table_param}_export_empty.csv'
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "text/csv",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
                "body": f"# No data found for {table_param} between {start_time} and {end_time}\n",
            }

        filename = query_params.get("filename") or f"{table_param}_export_{start_time}_{end_time}.csv"
        return csv_utils.create_csv_response(all_items, data_type, filename)
    except Exception as exc:
        return json_response(500, {"error": str(exc)})
