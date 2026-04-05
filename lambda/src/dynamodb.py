import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from schemas import DeviceApiKey
from utils import json_response


dynamodb = boto3.resource("dynamodb")

DETECTIONS_TABLE = "sensing-garden-detections"
CLASSIFICATIONS_TABLE = "sensing-garden-classifications"
MODELS_TABLE = "sensing-garden-models"
VIDEOS_TABLE = "sensing-garden-videos"
DEVICES_TABLE = "sensing-garden-devices"
ENVIRONMENTAL_READINGS_TABLE = "sensing-garden-environmental-readings"
DEPLOYMENTS_TABLE = "sensing-garden-deployments"
DEPLOYMENT_DEVICE_CONNECTIONS_TABLE = "sensing-garden-deployment-device-connections"
TRACKS_TABLE = "sensing-garden-tracks"
HEARTBEATS_TABLE = "sensing-garden-heartbeats"
DEVICE_API_KEYS_TABLE = os.environ.get("DEVICE_API_KEYS_TABLE", "sensing-garden-device-api-keys")

IMAGES_BUCKET = os.environ.get("IMAGES_BUCKET", "scl-sensing-garden-images")
VIDEOS_BUCKET = os.environ.get("VIDEOS_BUCKET", "scl-sensing-garden-videos")
DEFAULT_PAGE_LIMIT = 100


def add_device(
    device_id: str,
    created: Optional[str] = None,
    parent_device_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not device_id:
        raise ValueError("device_id is required")

    item = {
        "device_id": device_id,
        "created": created or datetime.now(timezone.utc).isoformat(),
    }
    if parent_device_id is not None:
        item["parent_device_id"] = parent_device_id
    dynamodb.Table(DEVICES_TABLE).put_item(Item=item)
    return item


def store_device_if_not_exists(device_id: str) -> Dict[str, Any]:
    if not device_id:
        raise ValueError("device_id is required")

    table = dynamodb.Table(DEVICES_TABLE)
    response = table.get_item(Key={"device_id": device_id})
    if "Item" in response and response["Item"].get("device_id") == device_id:
        return response["Item"]
    return add_device(device_id)


def upsert_device(
    device_id: str,
    created: Optional[str] = None,
    parent_device_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not device_id:
        raise ValueError("device_id is required")

    table = dynamodb.Table(DEVICES_TABLE)
    existing = table.get_item(Key={"device_id": device_id}).get("Item", {})
    item: Dict[str, Any] = {
        "device_id": device_id,
        "created": existing.get("created") or created or datetime.now(timezone.utc).isoformat(),
    }
    if parent_device_id is not None:
        item["parent_device_id"] = parent_device_id
    table.put_item(Item=item)
    return item


def store_device_api_key(data: Dict[str, Any]) -> Dict[str, Any]:
    item = DeviceApiKey(**data).model_dump()
    dynamodb.Table(DEVICE_API_KEYS_TABLE).put_item(Item=item)
    return item


def delete_device_api_key(device_id: str) -> None:
    dynamodb.Table(DEVICE_API_KEYS_TABLE).delete_item(Key={"device_id": device_id})


def get_active_device_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None

    response = dynamodb.Table(DEVICE_API_KEYS_TABLE).query(
        IndexName="api_key_index",
        KeyConditionExpression=Key("api_key").eq(api_key),
        Limit=1,
    )
    items = response.get("Items", [])
    if not items:
        return None
    item = items[0]
    if item.get("status") != "active":
        return None
    return item


def get_device_api_key_by_device_id(device_id: str) -> Optional[Dict[str, Any]]:
    if not device_id:
        return None
    response = dynamodb.Table(DEVICE_API_KEYS_TABLE).get_item(Key={"device_id": device_id})
    return response.get("Item")


def _delete_device_table_data(device_id: str, summary: Dict[str, Any]) -> None:
    for table_name, label in (
        (DETECTIONS_TABLE, "detections"),
        (CLASSIFICATIONS_TABLE, "classifications"),
        (VIDEOS_TABLE, "videos"),
        (ENVIRONMENTAL_READINGS_TABLE, "environmental_readings"),
    ):
        try:
            summary["deleted_counts"][label] = _delete_device_data_from_table(device_id, table_name)
        except Exception as exc:
            summary["deleted_counts"][label] = f"ERROR: {exc}"


def _delete_device_s3_data(device_id: str, summary: Dict[str, Any]) -> None:
    image_count = 0
    video_count = 0
    for bucket_name, prefix, label in (
        (IMAGES_BUCKET, "detection", "images"),
        (IMAGES_BUCKET, "classification", "images"),
        (VIDEOS_BUCKET, "videos", "videos"),
    ):
        try:
            deleted = _delete_s3_objects_for_device(device_id, bucket_name, f"{prefix}/{device_id}")
            if label == "images":
                image_count += deleted
            else:
                video_count += deleted
        except Exception as exc:
            print(f"[delete_device] Failed to delete s3 data {bucket_name}/{prefix}: {exc}")
    summary["deleted_counts"]["s3_images"] = image_count
    summary["deleted_counts"]["s3_videos"] = video_count


def _cascade_delete_device_data(device_id: str, summary: Dict[str, Any]) -> None:
    _delete_device_table_data(device_id, summary)
    _delete_device_s3_data(device_id, summary)


def _delete_device_data_from_table(device_id: str, table_name: str) -> int:
    table = dynamodb.Table(table_name)
    deleted_count = 0

    response = table.query(
        KeyConditionExpression=Key("device_id").eq(device_id),
        ProjectionExpression="device_id, #ts",
        ExpressionAttributeNames={"#ts": "timestamp"},
    )
    items_to_delete = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("device_id").eq(device_id),
            ProjectionExpression="device_id, #ts",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items_to_delete.extend(response.get("Items", []))

    with table.batch_writer() as batch_writer:
        for item in items_to_delete:
            batch_writer.delete_item(Key={"device_id": item["device_id"], "timestamp": item["timestamp"]})
            deleted_count += 1

    return deleted_count


def _delete_s3_objects_for_device(device_id: str, bucket_name: str, prefix: str) -> int:
    s3_client = boto3.client("s3")
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=f"{prefix}/")

    objects_to_delete = []
    for page in pages:
        if "Contents" in page:
            objects_to_delete.extend({"Key": obj["Key"]} for obj in page["Contents"])

    deleted_count = 0
    for index in range(0, len(objects_to_delete), 1000):
        batch = objects_to_delete[index:index + 1000]
        if not batch:
            continue
        s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": batch, "Quiet": True})
        deleted_count += len(batch)

    return deleted_count


def delete_device(device_id: str, cascade: bool = True) -> Dict[str, Any]:
    if not device_id:
        raise ValueError("device_id is required")

    summary: Dict[str, Any] = {
        "device_id": device_id,
        "device_deleted": False,
        "cascade": cascade,
        "deleted_counts": {},
    }

    try:
        if cascade:
            _cascade_delete_device_data(device_id, summary)

        dynamodb.Table(DEVICES_TABLE).delete_item(Key={"device_id": device_id})
        summary["device_deleted"] = True
        message = f"Device {device_id} deleted successfully"
        if cascade:
            message += " with all associated data"
        return json_response(200, {"message": message, "summary": summary})
    except Exception as exc:
        print(f"[delete_device] ERROR: {exc}")
        return json_response(500, {"error": str(exc), "summary": summary})


def delete_model(model_id: str) -> Dict[str, Any]:
    if not model_id:
        return json_response(400, {"error": "model_id is required"})

    try:
        table = dynamodb.Table(MODELS_TABLE)
        lookup = table.query(
            KeyConditionExpression=Key("id").eq(model_id),
            Limit=1,
            ScanIndexForward=False,
        )
        items = lookup.get("Items", [])
        if not items:
            return json_response(404, {"error": f"Model {model_id} not found"})

        existing = items[0]
        response = table.delete_item(
            Key={"id": model_id, "timestamp": existing["timestamp"]},
            ReturnValues="ALL_OLD",
        )
        deleted = response.get("Attributes")
        if not deleted:
            return json_response(404, {"error": f"Model {model_id} not found"})
        return json_response(200, {"message": f"Model {model_id} deleted successfully", "data": deleted})
    except Exception as exc:
        print(f"[delete_model] ERROR: {exc}")
        return json_response(500, {"error": str(exc)})


def get_devices(
    device_id: Optional[str] = None,
    created: Optional[str] = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False,
) -> Dict[str, Any]:
    table = dynamodb.Table(DEVICES_TABLE)
    params: Dict[str, Any] = {"Limit": min(limit, 5000) if limit else DEFAULT_PAGE_LIMIT}
    try:
        if next_token:
            try:
                params["ExclusiveStartKey"] = json.loads(next_token)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid next_token format") from exc

        filters = []
        if device_id:
            filters.append(Attr("device_id").eq(device_id))
        if created:
            filters.append(Attr("created").eq(created))
        if filters:
            expr = filters[0]
            for extra in filters[1:]:
                expr = expr & extra
            params["FilterExpression"] = expr
        response = table.scan(**params)
        items = response.get("Items", [])
        if sort_by and items and any(sort_by in item for item in items):
            items = sorted(items, key=lambda item: (sort_by in item, item.get(sort_by)), reverse=bool(sort_desc))
        result = {"items": items, "next_token": None}
        if response.get("LastEvaluatedKey"):
            result["next_token"] = json.dumps(response["LastEvaluatedKey"])
        return result
    except Exception as exc:
        print(f"[get_devices] ERROR: {exc}\n{traceback.format_exc()}")
        return {
            "items": [],
            "next_token": None,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def store_model_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if "id" not in data:
        raise ValueError("Model data must contain an 'id' field")
    if "type" not in data:
        data["type"] = "model"
    dynamodb.Table(MODELS_TABLE).put_item(Item=data)
    return json_response(200, {"message": "Model data stored successfully", "data": data})


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized_value = str(value)
    try:
        parsed = datetime.fromisoformat(normalized_value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y%m%d_%H%M%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(normalized_value, fmt)
            except ValueError:
                continue
        raise ValueError(f"Unsupported timestamp format: {value}")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _timestamp_in_range(timestamp: Optional[str], start_time: Optional[str], end_time: Optional[str]) -> bool:
    if not start_time and not end_time:
        return True
    parsed = _parse_time(timestamp)
    if parsed is None:
        return False
    start_dt = _parse_time(start_time)
    end_dt = _parse_time(end_time)
    if start_dt and parsed < start_dt:
        return False
    if end_dt and parsed > end_dt:
        return False
    return True


def _coerce_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except Exception:
        return None


def _paginate_all(table: Any, method: str, **kwargs: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    paginator = getattr(table, method)
    response = paginator(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = paginator(**kwargs)
        items.extend(response.get("Items", []))
    return items


def _list_all_device_ids() -> List[str]:
    devices_table = dynamodb.Table(DEVICES_TABLE)
    devices = _paginate_all(devices_table, "scan", ProjectionExpression="device_id")
    return [device["device_id"] for device in devices if device.get("device_id")]


def _sort_items(items: List[Dict[str, Any]], sort_by: Optional[str], sort_desc: bool) -> List[Dict[str, Any]]:
    if not sort_by:
        return items

    def sort_key(item: Dict[str, Any]) -> Any:
        if sort_by == "timestamp":
            return _parse_time(item.get("timestamp")) or datetime.min
        return item.get(sort_by)

    return sorted(items, key=sort_key, reverse=sort_desc)


def _parse_offset_token(next_token: Optional[str]) -> int:
    if not next_token:
        return 0
    try:
        data = json.loads(next_token)
        return max(int(data.get("offset", 0)), 0)
    except Exception as exc:
        raise ValueError("Invalid next_token format") from exc


def _build_offset_token(offset: int) -> str:
    return json.dumps({"offset": offset})


def _paginate_items(items: List[Dict[str, Any]], limit: int, next_token: Optional[str]) -> Dict[str, Any]:
    offset = _parse_offset_token(next_token)
    page = items[offset:offset + limit]
    result = {"items": page, "count": len(page)}
    if offset + limit < len(items):
        result["next_token"] = _build_offset_token(offset + limit)
    return result


def device_exists(device_id: str) -> bool:
    response = dynamodb.Table(DEVICES_TABLE).get_item(Key={"device_id": device_id})
    return "Item" in response


def get_deployment(deployment_id: str) -> Optional[Dict[str, Any]]:
    response = dynamodb.Table(DEPLOYMENTS_TABLE).get_item(Key={"deployment_id": deployment_id})
    return response.get("Item")


def list_deployments(
    limit: int = DEFAULT_PAGE_LIMIT,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False,
) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    params: Dict[str, Any] = {"Limit": min(limit, 5000) if limit else DEFAULT_PAGE_LIMIT}
    if next_token:
        try:
            params["ExclusiveStartKey"] = json.loads(next_token)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid next_token format") from exc
    response = table.scan(**params)
    items = _sort_items(response.get("Items", []), sort_by, sort_desc)
    result = {"items": items, "count": len(items)}
    if "LastEvaluatedKey" in response:
        result["next_token"] = json.dumps(response["LastEvaluatedKey"])
    return result


def store_deployment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    try:
        table.put_item(Item=data, ConditionExpression="attribute_not_exists(deployment_id)")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return json_response(409, {"error": f"Deployment {data['deployment_id']} already exists"})
        raise
    return json_response(200, {"message": "Deployment stored successfully", "deployment": data})


def update_deployment_data(deployment_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENTS_TABLE)
    if not get_deployment(deployment_id):
        return json_response(404, {"error": f"Deployment {deployment_id} not found"})

    update_expression = _build_update_expression(updates)
    response = table.update_item(
        Key={"deployment_id": deployment_id},
        **update_expression,
        ReturnValues="ALL_NEW",
    )
    return json_response(200, {"message": "Deployment updated successfully", "deployment": response.get("Attributes", {})})


def list_deployment_devices(deployment_id: str) -> List[Dict[str, Any]]:
    return _paginate_all(
        dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE),
        "query",
        KeyConditionExpression=Key("deployment_id").eq(deployment_id),
    )


def list_device_ids_for_deployment(deployment_id: str) -> List[str]:
    return [item["device_id"] for item in list_deployment_devices(deployment_id) if "device_id" in item]


def _build_update_expression(updates: Dict[str, Any]) -> Dict[str, Any]:
    expression_attribute_names = {f"#field_{key}": key for key in updates}
    expression_attribute_values = {f":val_{key}": value for key, value in updates.items()}
    update_expression = "SET " + ", ".join(
        f"#field_{key} = :val_{key}"
        for key in updates
    )
    return {
        "UpdateExpression": update_expression,
        "ExpressionAttributeNames": expression_attribute_names,
        "ExpressionAttributeValues": expression_attribute_values,
    }


def store_deployment_device_connection_data(data: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    try:
        table.put_item(
            Item=data,
            ConditionExpression="attribute_not_exists(deployment_id) AND attribute_not_exists(device_id)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return json_response(
                409,
                {"error": f"Deployment device {data['deployment_id']}/{data['device_id']} already exists"},
            )
        raise
    return json_response(200, data)


def update_deployment_device_connection(deployment_id: str, device_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    existing = table.get_item(Key={"deployment_id": deployment_id, "device_id": device_id}).get("Item")
    if not existing:
        return json_response(404, {"error": f"Deployment device {deployment_id}/{device_id} not found"})

    update_expression = _build_update_expression(updates)
    response = table.update_item(
        Key={"deployment_id": deployment_id, "device_id": device_id},
        **update_expression,
        ReturnValues="ALL_NEW",
    )
    return json_response(200, response.get("Attributes", {}))


def delete_deployment_device_connection(deployment_id: str, device_id: str) -> Dict[str, Any]:
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    response = table.delete_item(
        Key={"deployment_id": deployment_id, "device_id": device_id},
        ReturnValues="ALL_OLD",
    )
    deleted = response.get("Attributes")
    if not deleted:
        return json_response(404, {"error": f"Deployment device {deployment_id}/{device_id} not found"})
    return json_response(200, deleted)


def delete_deployment(deployment_id: str) -> Dict[str, Any]:
    deployment = get_deployment(deployment_id)
    if not deployment:
        return json_response(404, {"error": f"Deployment {deployment_id} not found"})

    connections = list_deployment_devices(deployment_id)
    table = dynamodb.Table(DEPLOYMENT_DEVICE_CONNECTIONS_TABLE)
    with table.batch_writer() as batch_writer:
        for connection in connections:
            batch_writer.delete_item(
                Key={"deployment_id": connection["deployment_id"], "device_id": connection["device_id"]}
            )

    dynamodb.Table(DEPLOYMENTS_TABLE).delete_item(Key={"deployment_id": deployment_id})
    return json_response(200, {"deployment": deployment, "deleted_connections": len(connections)})


def _load_table_items_for_devices(
    table_name: str,
    device_ids: Optional[List[str]],
    start_time: Optional[str],
    end_time: Optional[str],
) -> List[Dict[str, Any]]:
    table = dynamodb.Table(table_name)
    resolved_device_ids = _list_all_device_ids() if device_ids is None else device_ids
    if not resolved_device_ids:
        return []

    all_items: List[Dict[str, Any]] = []
    for device_id in resolved_device_ids:
        all_items.extend(_paginate_all(table, "query", KeyConditionExpression=Key("device_id").eq(device_id)))

    if start_time or end_time:
        all_items = [
            item for item in all_items if _timestamp_in_range(item.get("timestamp"), start_time, end_time)
        ]
    return all_items


def _load_tracks_for_devices(
    device_ids: Optional[List[str]],
    start_time: Optional[str],
    end_time: Optional[str],
) -> List[Dict[str, Any]]:
    table = dynamodb.Table(TRACKS_TABLE)
    resolved_device_ids = _list_all_device_ids() if device_ids is None else device_ids
    if not resolved_device_ids:
        return []

    all_items: List[Dict[str, Any]] = []
    for device_id in resolved_device_ids:
        all_items.extend(
            _paginate_all(
                table,
                "query",
                IndexName="device_id_index",
                KeyConditionExpression=Key("device_id").eq(device_id),
            )
        )

    if start_time or end_time:
        all_items = [
            item for item in all_items if _timestamp_in_range(item.get("timestamp"), start_time, end_time)
        ]
    return all_items


def _classification_confidence(item: Dict[str, Any], taxonomy_level: Optional[str]) -> Optional[float]:
    confidence_field = f"{taxonomy_level}_confidence" if taxonomy_level else "species_confidence"
    return _coerce_number(item.get(confidence_field))


def _filter_classification_items(
    items: List[Dict[str, Any]],
    model_id: Optional[str],
    min_confidence: Optional[float],
    taxonomy_level: Optional[str],
    selected_taxa: List[str],
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in items:
        if model_id and item.get("model_id") != model_id:
            continue
        if min_confidence is not None:
            confidence = _classification_confidence(item, taxonomy_level)
            if confidence is None or confidence < min_confidence:
                continue
        if taxonomy_level and selected_taxa and item.get(taxonomy_level) not in selected_taxa:
            continue
        filtered.append(item)
    return filtered


def list_classifications(
    device_ids: Optional[List[str]],
    model_id: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    min_confidence: Optional[float],
    taxonomy_level: Optional[str],
    selected_taxa: List[str],
    limit: int,
    next_token: Optional[str],
    sort_by: Optional[str],
    sort_desc: bool,
) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    items = _sort_items(items, sort_by or "timestamp", sort_desc)
    return _paginate_items(items, min(limit, 5000) if limit else DEFAULT_PAGE_LIMIT, next_token)


def count_classifications(
    device_ids: Optional[List[str]],
    model_id: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    min_confidence: Optional[float],
    taxonomy_level: Optional[str],
    selected_taxa: List[str],
) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    return {"count": len(items)}


def get_classification_taxa_count(
    device_ids: Optional[List[str]],
    model_id: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    min_confidence: Optional[float],
    taxonomy_level: str,
    selected_taxa: List[str],
    sort_desc: bool,
) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    counts: Dict[str, int] = {}
    for item in items:
        taxa_value = item.get(taxonomy_level)
        if taxa_value:
            counts[taxa_value] = counts.get(taxa_value, 0) + 1
    counted = [{"taxa": taxa, "count": count} for taxa, count in counts.items()]
    counted = sorted(counted, key=lambda item: item["count"], reverse=sort_desc)
    return {"counts": counted}


def _bucket_timestamps(
    items: List[Dict[str, Any]],
    start_time: str,
    end_time: Optional[str],
    interval_length: int,
    interval_unit: str,
) -> Dict[str, Any]:
    start_dt = _parse_time(start_time)
    if start_dt is None:
        raise ValueError("Invalid start_time")
    interval_delta = timedelta(hours=interval_length) if interval_unit == "h" else timedelta(days=interval_length)
    end_dt = _parse_time(end_time)
    if end_dt is None:
        parsed_items = [_parse_time(item.get("timestamp")) for item in items if _parse_time(item.get("timestamp"))]
        end_dt = (max(parsed_items) + interval_delta) if parsed_items else (start_dt + interval_delta)
    if end_dt <= start_dt:
        end_dt = start_dt + interval_delta
    bucket_count = max(int((end_dt - start_dt) / interval_delta), 1)
    return {
        "start_dt": start_dt,
        "end_dt": end_dt,
        "interval_delta": interval_delta,
        "bucket_count": bucket_count,
    }


def get_classification_time_series(
    device_ids: Optional[List[str]],
    model_id: Optional[str],
    start_time: str,
    end_time: Optional[str],
    min_confidence: Optional[float],
    taxonomy_level: Optional[str],
    selected_taxa: List[str],
    interval_length: int,
    interval_unit: str,
) -> Dict[str, Any]:
    items = _load_table_items_for_devices(CLASSIFICATIONS_TABLE, device_ids, start_time, end_time)
    items = _filter_classification_items(items, model_id, min_confidence, taxonomy_level, selected_taxa)
    bucket_config = _bucket_timestamps(items, start_time, end_time, interval_length, interval_unit)
    counts = [0] * bucket_config["bucket_count"]
    for item in items:
        item_time = _parse_time(item.get("timestamp"))
        if not item_time or item_time < bucket_config["start_dt"] or item_time >= bucket_config["end_dt"]:
            continue
        bucket_index = int((item_time - bucket_config["start_dt"]) / bucket_config["interval_delta"])
        if 0 <= bucket_index < len(counts):
            counts[bucket_index] += 1
    return {
        "counts": counts,
        "start_time": bucket_config["start_dt"].isoformat(),
        "interval_length": interval_length,
        "interval_unit": interval_unit,
    }


def get_environment_time_series(
    device_ids: Optional[List[str]],
    start_time: str,
    end_time: Optional[str],
    interval_length: int,
    interval_unit: str,
) -> Dict[str, Any]:
    items = _load_table_items_for_devices(ENVIRONMENTAL_READINGS_TABLE, device_ids, start_time, end_time)
    bucket_config = _bucket_timestamps(items, start_time, end_time, interval_length, interval_unit)
    metric_map = {
        "ambient_temperature": "temperature",
        "ambient_humidity": "humidity",
        "pm1p0": "pm1p0",
        "pm2p5": "pm2p5",
        "pm4p0": "pm4p0",
        "pm10p0": "pm10",
        "voc_index": "voc",
        "nox_index": "nox",
    }
    bucket_totals = {output_key: [0.0] * bucket_config["bucket_count"] for output_key in metric_map.values()}
    bucket_counts = {output_key: [0] * bucket_config["bucket_count"] for output_key in metric_map.values()}

    for item in items:
        item_time = _parse_time(item.get("timestamp"))
        if not item_time or item_time < bucket_config["start_dt"] or item_time >= bucket_config["end_dt"]:
            continue
        bucket_index = int((item_time - bucket_config["start_dt"]) / bucket_config["interval_delta"])
        if not (0 <= bucket_index < bucket_config["bucket_count"]):
            continue
        for source_key, output_key in metric_map.items():
            value = _coerce_number(item.get(source_key))
            if value is None:
                continue
            bucket_totals[output_key][bucket_index] += value
            bucket_counts[output_key][bucket_index] += 1

    result = {}
    for output_key in metric_map.values():
        result[output_key] = [
            (bucket_totals[output_key][index] / bucket_counts[output_key][index])
            if bucket_counts[output_key][index]
            else 0
            for index in range(bucket_config["bucket_count"])
        ]
    result.update(
        {
            "start_time": bucket_config["start_dt"].isoformat(),
            "interval_length": interval_length,
            "interval_unit": interval_unit,
        }
    )
    return result


def list_tracks(
    device_ids: Optional[List[str]],
    start_time: Optional[str],
    end_time: Optional[str],
    limit: int,
    next_token: Optional[str],
    sort_by: Optional[str],
    sort_desc: bool,
) -> Dict[str, Any]:
    items = _load_tracks_for_devices(device_ids, start_time, end_time)
    items = _sort_items(items, sort_by or "timestamp", sort_desc)
    return _paginate_items(items, min(limit, 5000) if limit else DEFAULT_PAGE_LIMIT, next_token)


def count_tracks(
    device_ids: Optional[List[str]],
    start_time: Optional[str],
    end_time: Optional[str],
) -> Dict[str, Any]:
    items = _load_tracks_for_devices(device_ids, start_time, end_time)
    return {"count": len(items)}


def get_track(track_id: str) -> Optional[Dict[str, Any]]:
    response = dynamodb.Table(TRACKS_TABLE).query(
        KeyConditionExpression=Key("track_id").eq(track_id),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def get_latest_heartbeats() -> Dict[str, Any]:
    table = dynamodb.Table(HEARTBEATS_TABLE)
    items: List[Dict[str, Any]] = []
    for device_id in _list_all_device_ids():
        response = table.query(
            KeyConditionExpression=Key("device_id").eq(device_id),
            ScanIndexForward=False,
            Limit=1,
        )
        latest = response.get("Items", [])
        if latest:
            items.append(latest[0])
    items = _sort_items(items, "timestamp", True)
    return {"items": items, "count": len(items)}


def put_track(item: Dict[str, Any]) -> None:
    dynamodb.Table(TRACKS_TABLE).put_item(Item=item)


def put_heartbeat(item: Dict[str, Any]) -> None:
    dynamodb.Table(HEARTBEATS_TABLE).put_item(Item=item)


def _load_items_for_query_data(table_type: str, device_id: Optional[str], model_id: Optional[str]) -> List[Dict[str, Any]]:
    table_name = {
        "detection": DETECTIONS_TABLE,
        "classification": CLASSIFICATIONS_TABLE,
        "model": MODELS_TABLE,
        "video": VIDEOS_TABLE,
        "environmental_reading": ENVIRONMENTAL_READINGS_TABLE,
    }[table_type]
    table = dynamodb.Table(table_name)

    if table_type in {"detection", "classification", "video", "environmental_reading"} and device_id:
        return _paginate_all(table, "query", KeyConditionExpression=Key("device_id").eq(device_id))

    if table_type == "model" and model_id:
        try:
            lookup = table.query(KeyConditionExpression=Key("id").eq(model_id))
            return lookup.get("Items", [])
        except Exception:
            item = table.get_item(Key={"id": model_id}).get("Item")
            return [item] if item else []

    if table_type in {"detection", "classification", "video", "environmental_reading"}:
        all_items: List[Dict[str, Any]] = []
        for known_device_id in _list_all_device_ids():
            all_items.extend(_paginate_all(table, "query", KeyConditionExpression=Key("device_id").eq(known_device_id)))
        return all_items

    return _paginate_all(table, "scan")


def _filter_items_for_query_data(
    table_type: str,
    items: List[Dict[str, Any]],
    device_id: Optional[str],
    model_id: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in items:
        if table_type == "model":
            if device_id and item.get("device_id") != device_id:
                continue
            if model_id and item.get("id") != model_id:
                continue
        elif table_type in {"detection", "classification", "video"}:
            if device_id and item.get("device_id") != device_id:
                continue
            if model_id and item.get("model_id") != model_id:
                continue
        elif table_type == "environmental_reading" and device_id and item.get("device_id") != device_id:
            continue

        if (start_time or end_time) and not _timestamp_in_range(item.get("timestamp"), start_time, end_time):
            continue
        filtered.append(item)
    return filtered


def count_data(
    table_type: str,
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Dict[str, Any]:
    if table_type not in ["detection", "classification", "model", "video", "environmental_reading"]:
        raise ValueError(f"Invalid table_type: {table_type}")
    items = _load_items_for_query_data(table_type, device_id, model_id)
    items = _filter_items_for_query_data(table_type, items, device_id, model_id, start_time, end_time)
    return {"count": len(items)}


def query_data(
    table_type: str,
    device_id: Optional[str] = None,
    model_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    next_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False,
) -> Dict[str, Any]:
    if table_type not in ["detection", "classification", "model", "video", "environmental_reading"]:
        raise ValueError(f"Invalid table_type: {table_type}")

    items = _load_items_for_query_data(table_type, device_id, model_id)
    items = _filter_items_for_query_data(table_type, items, device_id, model_id, start_time, end_time)
    items = _sort_items(items, sort_by, sort_desc)
    return _paginate_items(items, min(limit, 5000) if limit else DEFAULT_PAGE_LIMIT, next_token)
