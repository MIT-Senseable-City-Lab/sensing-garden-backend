# CSV Export Utility for Sensing Garden Backend

This document describes the comprehensive CSV flattening utility built for the sensing-garden-backend. The utility handles all complex nested data structures from DynamoDB tables and exports them as properly formatted CSV files.

## Overview

The CSV export utility provides robust flattening of nested DynamoDB data structures into flat CSV columns with proper handling of all data types found in the sensing-garden tables:

- **sensor_detections** - Insect detection results with bounding boxes
- **sensor_classifications** - Species classification with taxonomic data, confidence scores, and environmental readings
- **models** - ML model information
- **videos** - Time-lapse video metadata
- **environmental_readings** - Environmental sensor data
- **devices** - Device registry information

## Features

### Data Type Handling
- ✅ **Decimal types**: Converted from DynamoDB Decimal to float strings
- ✅ **Nested objects**: Flattened to prefixed key-value pairs
- ✅ **Arrays**: Special handling for bounding boxes, JSON encoding for others
- ✅ **Null/None values**: Converted to empty strings
- ✅ **Boolean values**: Converted to "true"/"false"
- ✅ **Complex objects**: JSON-encoded when necessary
- ✅ **Special characters**: Proper CSV escaping

### Nested Structure Flattening

#### Bounding Box Arrays
```
[xmin, ymin, xmax, ymax] → bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax
```

#### Location Objects
```json
{
  "lat": 40.7128,
  "long": -74.0060,
  "alt": 10.5
}
```
→ `latitude`, `longitude`, `altitude`

#### Classification Data
```json
{
  "family": [
    {"name": "Nymphalidae", "confidence": 0.95},
    {"name": "Pieridae", "confidence": 0.05}
  ]
}
```
→ `classification_family_count`, `classification_family_1_name`, `classification_family_1_confidence`, etc.

#### Metadata Objects
```json
{
  "camera": {
    "model": "RaspberryPi Camera v2",
    "settings": {
      "iso": 100
    }
  }
}
```
→ `metadata_camera_model`, `metadata_camera_settings_iso`

## API Endpoints

The utility provides CSV export endpoints for all data tables:

### Available Endpoints
- `GET /detections/csv` - Export detection data
- `GET /classifications/csv` - Export classification data
- `GET /models/csv` - Export model data
- `GET /videos/csv` - Export video metadata
- `GET /environment/csv` - Export environmental readings
- `GET /devices/csv` - Export device information

### Query Parameters

All endpoints support the same filtering and pagination parameters as their JSON counterparts:

- `device_id` - Filter by specific device
- `model_id` - Filter by specific model (where applicable)
- `start_time` - Filter by start timestamp (ISO 8601 format)
- `end_time` - Filter by end timestamp (ISO 8601 format)
- `limit` - Maximum number of records (default: 5000 for CSV)
- `next_token` - Pagination token
- `sort_by` - Sort field
- `sort_desc` - Sort in descending order (true/false)
- `filename` - Custom filename for download

### Example Requests

```bash
# Export all classifications for a specific device
curl "https://api.example.com/classifications/csv?device_id=garden-pi-001"

# Export detections from a date range with custom filename
curl "https://api.example.com/detections/csv?start_time=2023-07-15T00:00:00Z&end_time=2023-07-15T23:59:59Z&filename=daily_detections.csv"

# Export environmental readings sorted by timestamp
curl "https://api.example.com/environment/csv?sort_by=timestamp&sort_desc=true&limit=1000"
```

## Column Ordering

The CSV utility implements intelligent column ordering for consistency and usability:

### Priority Fields (appear first in order):
1. `device_id`
2. `timestamp` 
3. `model_id`
4. `id`
5. `name`
6. `type`
7. `family`, `genus`, `species`
8. `family_confidence`, `genus_confidence`, `species_confidence`
9. `bbox_xmin`, `bbox_ymin`, `bbox_xmax`, `bbox_ymax`
10. `latitude`, `longitude`, `altitude`
11. `image_key`, `image_bucket`, `video_key`, `video_bucket`
12. `track_id`, `created`, `description`, `version`

### Remaining Fields
All other fields are sorted alphabetically after the priority fields.

## Usage Examples

### Programmatic Usage

```python
from csv_utils import generate_complete_csv, create_csv_response

# Generate CSV content from DynamoDB items
items = [
    {
        'device_id': 'garden-pi-001',
        'timestamp': '2023-07-15T10:30:00Z',
        'bounding_box': [10, 20, 30, 40],
        'location': {'lat': 40.7128, 'long': -74.0060}
    }
]

# Generate complete CSV content
csv_content = generate_complete_csv(items, 'detection')
print(csv_content)

# Generate HTTP response for download
response = create_csv_response(items, 'detection', 'my_export.csv')
```

### Lambda Handler Integration

```python
def handle_csv_detections(event):
    query_params = event.get('queryStringParameters', {}) or {}
    
    # Query data using existing DynamoDB functions
    result = dynamodb.query_data(
        'detection',
        device_id=query_params.get('device_id'),
        start_time=query_params.get('start_time'),
        end_time=query_params.get('end_time'),
        limit=int(query_params.get('limit', 5000))
    )
    
    # Convert to CSV and return as download
    filename = query_params.get('filename')
    return csv_utils.create_csv_response(result['items'], 'detection', filename)
```

## Sample Output

### Detection CSV
```csv
device_id,timestamp,model_id,bbox_xmin,bbox_ymin,bbox_xmax,bbox_ymax,image_key,image_bucket
garden-pi-001,2023-07-15T08:30:15.123Z,yolov8n-insects-v2.1,245.7,178.3,312.9,234.8,detection/garden-pi-001/2023-07-15-08-30-15.jpg,scl-sensing-garden-images
```

### Classification CSV (with environmental data)
```csv
device_id,timestamp,model_id,family,genus,species,family_confidence,genus_confidence,species_confidence,bbox_xmin,bbox_ymin,bbox_xmax,bbox_ymax,latitude,longitude,altitude,ambient_temperature,ambient_humidity,pm1p0,pm2p5,voc_index,classification_family_count,classification_family_1_name,classification_family_1_confidence
garden-pi-001,2023-07-15T10:22:35.789Z,efficientnet-v1.3,Nymphalidae,Vanessa,cardui,0.9523,0.8734,0.8156,198.4,145.7,276.8,213.9,40.712776,-74.005974,12.3,24.7,62.3,8.7,12.4,142.0,3,Nymphalidae,0.9523
```

## Error Handling

The utility provides comprehensive error handling:

- **Invalid data types**: Safely converts or JSON-encodes complex objects
- **Missing fields**: Empty strings for missing values
- **Malformed structures**: Graceful handling of incomplete nested objects
- **Large datasets**: Efficient processing with configurable limits
- **Network errors**: Proper HTTP error responses with details

## Testing

The utility includes comprehensive test coverage:

```bash
# Run CSV utility tests
python -m pytest tests/test_csv_utils.py -v

# Run CSV handler integration tests  
python -m pytest tests/test_csv_handlers.py -v

# Run demonstration script
python csv_demo.py
```

## Performance Considerations

- **Memory efficient**: Streaming CSV generation using StringIO
- **Large datasets**: Configurable limits with pagination support
- **DynamoDB optimization**: Uses existing optimized query functions
- **Lambda compatible**: Designed for AWS Lambda execution environment

## Security

- **Input validation**: All query parameters are validated
- **CSV injection prevention**: Proper escaping of special characters
- **No sensitive data exposure**: Only exports data accessible via existing API endpoints

## Files

- `/lambda/src/csv_utils.py` - Main CSV utility functions
- `/lambda/src/handler.py` - Updated with CSV endpoint handlers
- `/tests/test_csv_utils.py` - Comprehensive unit tests
- `/tests/test_csv_handlers.py` - Integration tests
- `/csv_demo.py` - Demonstration script
- `/CSV_EXPORT_README.md` - This documentation

## Integration Checklist

- ✅ CSV flattening utility implemented
- ✅ Handler endpoints added for all tables
- ✅ Routing added to main Lambda handler
- ✅ Comprehensive test coverage
- ✅ Error handling implemented
- ✅ Documentation completed
- ✅ Demonstration script created

The CSV export utility is now ready for deployment and use in production!