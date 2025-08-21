"""
CSV flattening utility for Sensing Garden backend.

This module provides functions to flatten nested DynamoDB data structures
into CSV format with proper handling of all data types found in the
sensing-garden tables.
"""

import csv
import io
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
import json


def _safe_str(value: Any) -> str:
    """Convert any value to a safe string representation for CSV."""
    if value is None:
        return ""
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, Decimal):
        return str(float(value))
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        return value
    elif isinstance(value, (list, dict)):
        # Convert complex objects to JSON strings
        return json.dumps(value)
    else:
        return str(value)


def _flatten_bounding_box(bbox: List[Union[int, float, Decimal]]) -> Dict[str, str]:
    """Flatten bounding box array [xmin, ymin, xmax, ymax] to separate columns."""
    if not bbox or len(bbox) != 4:
        return {
            'bbox_xmin': '',
            'bbox_ymin': '',
            'bbox_xmax': '',
            'bbox_ymax': ''
        }
    
    return {
        'bbox_xmin': _safe_str(bbox[0]),
        'bbox_ymin': _safe_str(bbox[1]),
        'bbox_xmax': _safe_str(bbox[2]),
        'bbox_ymax': _safe_str(bbox[3])
    }


def _flatten_location(location: Dict[str, Any]) -> Dict[str, str]:
    """Flatten location object {lat, long, alt} to separate columns."""
    if not location or not isinstance(location, dict):
        return {
            'latitude': '',
            'longitude': '',
            'altitude': ''
        }
    
    return {
        'latitude': _safe_str(location.get('lat', '')),
        'longitude': _safe_str(location.get('long', '')),
        'altitude': _safe_str(location.get('alt', ''))
    }


def _flatten_classification_data(classification_data: Dict[str, Any]) -> Dict[str, str]:
    """Flatten classification_data nested object to key-value pairs."""
    if not classification_data or not isinstance(classification_data, dict):
        return {}
    
    flattened = {}
    
    for level in ['family', 'genus', 'species']:
        if level in classification_data and isinstance(classification_data[level], list):
            candidates = classification_data[level]
            
            # Add count of candidates for each level
            flattened[f'classification_{level}_count'] = str(len(candidates))
            
            # Add top 3 candidates with their confidence scores
            for i, candidate in enumerate(candidates[:3]):
                if isinstance(candidate, dict) and 'name' in candidate and 'confidence' in candidate:
                    flattened[f'classification_{level}_{i+1}_name'] = _safe_str(candidate['name'])
                    flattened[f'classification_{level}_{i+1}_confidence'] = _safe_str(candidate['confidence'])
    
    return flattened


def _flatten_metadata(metadata: Dict[str, Any], prefix: str = 'metadata') -> Dict[str, str]:
    """Flatten metadata object to prefixed key-value pairs."""
    if not metadata or not isinstance(metadata, dict):
        return {}
    
    flattened = {}
    
    def _flatten_nested(obj: Any, current_prefix: str) -> None:
        """Recursively flatten nested objects."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{current_prefix}_{key}"
                if isinstance(value, dict):
                    _flatten_nested(value, new_key)
                elif isinstance(value, list):
                    # Convert lists to JSON strings to avoid further complexity
                    flattened[new_key] = json.dumps(value)
                else:
                    flattened[new_key] = _safe_str(value)
        else:
            flattened[current_prefix] = _safe_str(obj)
    
    _flatten_nested(metadata, prefix)
    return flattened


def _flatten_environment_data(item: Dict[str, Any]) -> Dict[str, str]:
    """Extract and flatten environmental sensor data."""
    env_fields = [
        'pm1p0', 'pm2p5', 'pm4p0', 'pm10p0',
        'temperature', 'humidity', 'ambient_temperature', 'ambient_humidity',
        'light_level', 'pressure', 'soil_moisture', 
        'wind_speed', 'wind_direction', 'uv_index',
        'voc_index', 'nox_index'
    ]
    
    flattened = {}
    for field in env_fields:
        if field in item:
            flattened[field] = _safe_str(item[field])
    
    return flattened


def flatten_dynamodb_item(item: Dict[str, Any], table_type: str) -> Dict[str, str]:
    """
    Flatten a single DynamoDB item for CSV export.
    
    Args:
        item: DynamoDB item (already processed by DynamoDBEncoder)
        table_type: Type of table ('detection', 'classification', 'model', 'video', 'environmental_reading')
    
    Returns:
        Dictionary with flattened key-value pairs suitable for CSV
    """
    flattened = {}
    
    # Handle standard fields first
    standard_fields = [
        'device_id', 'timestamp', 'model_id', 'id', 'name', 'description', 'version', 'type',
        'image_key', 'image_bucket', 'video_key', 'video_bucket',
        'family', 'genus', 'species', 'family_confidence', 'genus_confidence', 'species_confidence',
        'track_id', 'created'
    ]
    
    for field in standard_fields:
        if field in item:
            flattened[field] = _safe_str(item[field])
    
    # Handle special nested structures
    if 'bounding_box' in item:
        bbox_flat = _flatten_bounding_box(item['bounding_box'])
        flattened.update(bbox_flat)
    
    if 'location' in item:
        location_flat = _flatten_location(item['location'])
        flattened.update(location_flat)
    
    if 'classification_data' in item:
        classification_flat = _flatten_classification_data(item['classification_data'])
        flattened.update(classification_flat)
    
    if 'metadata' in item:
        metadata_flat = _flatten_metadata(item['metadata'])
        flattened.update(metadata_flat)
    
    # Handle environmental data
    env_flat = _flatten_environment_data(item)
    flattened.update(env_flat)
    
    # Handle any remaining fields not covered above
    handled_fields = set(standard_fields + ['bounding_box', 'location', 'classification_data', 'metadata'])
    handled_fields.update(env_flat.keys())
    
    for key, value in item.items():
        if key not in handled_fields:
            # Handle any other complex objects
            if isinstance(value, (dict, list)):
                if key == 'environment':
                    # Special case: flatten environment object
                    if isinstance(value, dict):
                        for env_key, env_value in value.items():
                            flattened[f"environment_{env_key}"] = _safe_str(env_value)
                else:
                    flattened[key] = json.dumps(value)
            else:
                flattened[key] = _safe_str(value)
    
    return flattened


def generate_csv_from_dynamodb_items(
    items: List[Dict[str, Any]], 
    table_type: str,
    include_header: bool = True
) -> Tuple[Optional[str], List[str]]:
    """
    Generate CSV content from a list of DynamoDB items.
    
    Args:
        items: List of DynamoDB items (already processed by DynamoDBEncoder)
        table_type: Type of table ('detection', 'classification', 'model', 'video', 'environmental_reading')
        include_header: Whether to include CSV header row
    
    Returns:
        Tuple of (header_row, data_rows) where:
        - header_row is CSV header string or None if include_header=False
        - data_rows is list of CSV row strings
    """
    if not items:
        return (None, [])
    
    # Flatten all items to determine the complete set of columns
    flattened_items = []
    all_columns = set()
    
    for item in items:
        flattened = flatten_dynamodb_item(item, table_type)
        flattened_items.append(flattened)
        all_columns.update(flattened.keys())
    
    # Sort columns for consistent ordering
    # Prioritize common fields first, then sort alphabetically
    priority_fields = [
        'device_id', 'timestamp', 'model_id', 'id', 'name', 'type',
        'family', 'genus', 'species', 
        'family_confidence', 'genus_confidence', 'species_confidence',
        'bbox_xmin', 'bbox_ymin', 'bbox_xmax', 'bbox_ymax',
        'latitude', 'longitude', 'altitude',
        'image_key', 'image_bucket', 'video_key', 'video_bucket',
        'track_id', 'created', 'description', 'version'
    ]
    
    ordered_columns = []
    # Add priority fields if they exist
    for field in priority_fields:
        if field in all_columns:
            ordered_columns.append(field)
            all_columns.remove(field)
    
    # Add remaining columns alphabetically
    ordered_columns.extend(sorted(all_columns))
    
    # Generate CSV content
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    
    header_row = None
    if include_header:
        writer.writerow(ordered_columns)
        output.seek(0)
        header_row = output.getvalue().strip()
        output.seek(0)
        output.truncate(0)
    
    # Write data rows
    data_rows = []
    for flattened_item in flattened_items:
        row_data = []
        for column in ordered_columns:
            value = flattened_item.get(column, '')
            row_data.append(value)
        
        writer.writerow(row_data)
        output.seek(0)
        row_content = output.getvalue().strip()
        data_rows.append(row_content)
        output.seek(0)
        output.truncate(0)
    
    output.close()
    return (header_row, data_rows)


def generate_complete_csv(
    items: List[Dict[str, Any]], 
    table_type: str
) -> str:
    """
    Generate complete CSV content with header and data rows.
    
    Args:
        items: List of DynamoDB items (already processed by DynamoDBEncoder)
        table_type: Type of table ('detection', 'classification', 'model', 'video', 'environmental_reading')
    
    Returns:
        Complete CSV content as string
    """
    header, data_rows = generate_csv_from_dynamodb_items(items, table_type, include_header=True)
    
    if not header and not data_rows:
        return ""
    
    csv_lines = []
    if header:
        csv_lines.append(header)
    csv_lines.extend(data_rows)
    
    return '\n'.join(csv_lines)


def create_csv_response(
    items: List[Dict[str, Any]], 
    table_type: str, 
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create HTTP response for CSV download.
    
    Args:
        items: List of DynamoDB items (already processed by DynamoDBEncoder)
        table_type: Type of table ('detection', 'classification', 'model', 'video', 'environmental_reading')
        filename: Optional filename for download
    
    Returns:
        HTTP response dictionary suitable for Lambda
    """
    try:
        csv_content = generate_complete_csv(items, table_type)
        
        if not filename:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"sensing_garden_{table_type}s_{timestamp}.csv"
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/csv',
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*'
            },
            'body': csv_content
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': f'Failed to generate CSV: {str(e)}'
            })
        }