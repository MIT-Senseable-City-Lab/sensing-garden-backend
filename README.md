# Sensing Garden Backend

Backend services for the Sensing Garden project, including Lambda functions for image processing and environmental data collection, DynamoDB for data storage, and S3 for image storage.

⚠️ **Note:** The Python client (`sensing_garden_client`) and its accompanying tests have been moved to the separate [`sensing-garden-client`](https://github.com/daydemir/sensing-garden-client) repository. This backend repository now contains only infrastructure and AWS-related code.

## Project Structure

- `lambda/`: Contains the Lambda function code
  - `src/`: Source code for Lambda functions
    - `handler.py`: Main Lambda handler functions
    - `dynamodb.py`: DynamoDB interaction functions
- `terraform/`: Infrastructure as Code using Terraform

## Setup

### Prerequisites

- Python 3.9+
- [Poetry](https://python-poetry.org/) for dependency management
- AWS account with appropriate permissions
- AWS CLI configured with your credentials

### Environment Variables

Set up API configuration using environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SENSING_GARDEN_API_KEY` | **Required** | API authentication key |
| `API_BASE_URL` | **Required** | Backend API endpoint |

```bash
# Set these in your shell or .env file (don't commit .env to git)
export SENSING_GARDEN_API_KEY="your-api-key"
export API_BASE_URL="https://your-api-endpoint.execute-api.region.amazonaws.com"
```




## API Endpoints

The backend provides the following REST API endpoints:

### Core Data Endpoints
- `GET /models` - Retrieve ML model information
- `POST /models` - Submit new model data
- `GET /detections` - Retrieve insect detection results with bounding boxes
- `POST /detections` - Submit new detection data
- `GET /classifications` - Retrieve insect species classification results
- `POST /classifications` - Submit new classification data
- `GET /videos` - Retrieve time-lapse videos of garden activity
- `POST /videos` - Upload new video data

### Environmental Data Endpoints
- `GET /environment` - Retrieve environmental sensor readings from garden monitoring devices
- `POST /environment` - Submit new environmental sensor data
- `GET /environment/count` - Get count of environmental readings

### Count Endpoints
- `GET /models/count` - Get count of models
- `GET /detections/count` - Get count of detections
- `GET /classifications/count` - Get count of classifications
- `GET /videos/count` - Get count of videos

### Environmental Data Format
Environmental readings include:
- **Particulate Matter**: PM1.0, PM2.5, PM4.0, PM10.0 concentrations (μg/m³)
- **Climate**: Ambient humidity (%) and temperature (°C)
- **Air Quality**: VOC (Volatile Organic Compounds) index and NOx (Nitrogen Oxides) index
- **Location**: GPS coordinates (latitude, longitude, optional altitude)

### Query Parameters

All GET endpoints support the following query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_id` | String | Optional | Filter results by specific device |
| `start_time` | ISO 8601 | Optional | Filter results from this timestamp |
| `end_time` | ISO 8601 | Optional | Filter results until this timestamp |
| `limit` | Integer | Optional | Maximum number of results to return |
| `sort_by` | String | Optional | Field to sort by (default: timestamp) |
| `sort_desc` | Boolean | Optional | Sort in descending order (default: false) |

## API Examples

### Authentication
All API requests require the `X-API-Key` header with your API key:

```bash
curl -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" "${API_BASE_URL}/models"
```

**Note:** If using the custom domain `api.sensinggarden.com`, all endpoints require the `/v1/` prefix:
```bash
curl -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" "https://api.sensinggarden.com/v1/models"
```

### Classifications

#### POST Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_id` | String | **Required** | Unique identifier for the device |
| `model_id` | String | **Required** | Identifier for the ML model used |
| `image` | String (Base64) | **Required** | Base64-encoded image data |
| `family` | String | **Required** | Taxonomic family classification |
| `genus` | String | Optional | Taxonomic genus classification |
| `species` | String | Optional | Taxonomic species classification |
| `confidences` | Object | Optional | Confidence scores for each taxonomic level |
| `location` | Object | Optional | GPS coordinates (see Location Object below) |
| `data` | Object | Optional | Environmental sensor data (see Environmental Data Object below) |
| `track_id` | String | Optional | Tracking identifier for the detected insect |
| `bounding_box` | Array[4] | Optional | Bounding box coordinates [x, y, width, height] |

#### Location Object (when provided)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | Number | **Required** | Latitude coordinate |
| `long` | Number | **Required** | Longitude coordinate |
| `alt` | Number | Optional | Altitude in meters |

#### Environmental Data Object (when provided)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pm1p0` | Number | Optional | PM1.0 concentration (μg/m³) |
| `pm2p5` | Number | Optional | PM2.5 concentration (μg/m³) |
| `pm4p0` | Number | Optional | PM4.0 concentration (μg/m³) |
| `pm10p0` | Number | Optional | PM10.0 concentration (μg/m³) |
| `ambient_humidity` | Number | Optional | Ambient humidity (%) |
| `ambient_temperature` | Number | Optional | Ambient temperature (°C) |
| `voc_index` | Number | Optional | Volatile Organic Compounds index |
| `nox_index` | Number | Optional | Nitrogen Oxides index |

#### Minimal Classification Request (Required Fields Only)
Submit basic insect classification data:

```bash
curl -X POST "${API_BASE_URL}/classifications" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-001",
    "model_id": "yolov8n-insects-v1.2",
    "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    "family": "Nymphalidae",
    "genus": "Vanessa",
    "species": "cardui",
    "family_confidence": 0.95,
    "genus_confidence": 0.87,
    "species_confidence": 0.82
  }'
```

#### Basic Classification Request
Submit insect classification data with taxonomic hierarchy:

```bash
curl -X POST "${API_BASE_URL}/classifications" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-001",
    "model_id": "yolov8n-insects-v1.2",
    "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    "family": "Nymphalidae",
    "genus": "Vanessa", 
    "species": "cardui",
    "family_confidence": 0.95,
    "genus_confidence": 0.87,
    "species_confidence": 0.82
  }'
```

#### Classification with Environmental Data
Submit classification including location and environmental sensor readings:

```bash
curl -X POST "${API_BASE_URL}/classifications" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-001",
    "model_id": "yolov8n-insects-v1.2",
    "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    "family": "Apidae",
    "genus": "Apis",
    "species": "mellifera",
    "family_confidence": 0.92,
    "genus_confidence": 0.85,
    "species_confidence": 0.78,
    "location": {
      "lat": 40.7128,
      "long": -74.0060,
      "alt": 10.5
    },
    "data": {
      "pm1p0": 12.5,
      "pm2p5": 18.3,
      "pm4p0": 22.1,
      "pm10p0": 28.7,
      "ambient_humidity": 65.2,
      "ambient_temperature": 23.4,
      "voc_index": 150,
      "nox_index": 75
    },
    "track_id": "butterfly_001",
    "bounding_box": [150, 200, 50, 40]
  }'
```

#### Query Classifications
Retrieve classification data with filtering:

```bash
# Get recent classifications from specific device
curl -G "${API_BASE_URL}/classifications" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d device_id=garden-pi-001 \
  -d start_time=2024-08-20T00:00:00Z \
  -d limit=50 \
  -d sort_desc=true
```

### Detections

#### POST Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_id` | String | **Required** | Unique identifier for the device |
| `model_id` | String | **Required** | Identifier for the ML model used |
| `image` | String (Base64) | **Required** | Base64-encoded image data |
| `bounding_box` | Array[4] | **Required** | Bounding box coordinates [x, y, width, height] |
| `timestamp` | ISO 8601 | Optional | Detection timestamp (defaults to current time) |

#### Submit Detection Data
Submit insect detection with bounding box coordinates:

```bash
curl -X POST "${API_BASE_URL}/detections" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-002",
    "model_id": "yolov8n-insects-v1.2",
    "timestamp": "2024-08-21T14:30:00Z",
    "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    "bounding_box": [125, 180, 75, 60]
  }'
```

### Environmental Data

#### POST Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_id` | String | **Required** | Unique identifier for the device |
| `data` | Object | **Required** | Environmental sensor data (see Environmental Data Object below) |
| `timestamp` | ISO 8601 | Optional | Reading timestamp (defaults to current time) |
| `location` | Object | Optional | GPS coordinates (see Location Object below) |

#### Location Object (when provided)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | Number | **Required** | Latitude coordinate |
| `long` | Number | **Required** | Longitude coordinate |
| `alt` | Number | Optional | Altitude in meters |

#### Environmental Data Object

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pm1p0` | Number | Optional | PM1.0 concentration (μg/m³) |
| `pm2p5` | Number | Optional | PM2.5 concentration (μg/m³) |
| `pm4p0` | Number | Optional | PM4.0 concentration (μg/m³) |
| `pm10p0` | Number | Optional | PM10.0 concentration (μg/m³) |
| `ambient_humidity` | Number | Optional | Ambient humidity (%) |
| `ambient_temperature` | Number | Optional | Ambient temperature (°C) |
| `voc_index` | Number | Optional | Volatile Organic Compounds index |
| `nox_index` | Number | Optional | Nitrogen Oxides index |

#### Minimal Environmental Data Request (Required Fields Only)
Submit basic environmental data:

```bash
curl -X POST "${API_BASE_URL}/environment" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-001",
    "data": {}
  }'
```

#### Complete Environmental Data Request
Submit comprehensive environmental sensor data:

```bash
curl -X POST "${API_BASE_URL}/environment" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-001",
    "timestamp": "2024-08-21T14:30:00Z",
    "location": {
      "lat": 40.7128,
      "long": -74.0060,
      "alt": 15.0
    },
    "data": {
      "pm1p0": 8.2,
      "pm2p5": 15.7,
      "pm4p0": 19.3,
      "pm10p0": 24.1,
      "ambient_humidity": 62.8,
      "ambient_temperature": 24.7,
      "voc_index": 135,
      "nox_index": 68
    }
  }'
```

#### Query Environmental Data
Retrieve environmental readings with time-based filtering:

```bash
# Get last 24 hours of environmental data
curl -G "${API_BASE_URL}/environment" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d device_id=garden-pi-001 \
  -d start_time=2024-08-20T14:30:00Z \
  -d end_time=2024-08-21T14:30:00Z \
  -d limit=100 \
  -d sort_by=timestamp
```

### Models

#### POST Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | String | **Required** | Unique identifier for the model |
| `name` | String | **Required** | Human-readable model name |
| `version` | String | **Required** | Model version identifier |
| `metadata` | Object | Optional | Additional model information (framework, classes, etc.) |

#### Register a Model
Submit new ML model information:

```bash
curl -X POST "${API_BASE_URL}/models" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "model_id": "yolov8n-insects-v1.3",
    "name": "YOLOv8 Nano Insect Detection",
    "version": "1.3.0",
    "metadata": {
      "framework": "YOLOv8",
      "classes": ["bee", "butterfly", "fly", "moth"],
      "input_size": [640, 640],
      "accuracy": 0.89
    }
  }'
```

### Videos

#### POST Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_id` | String | **Required** | Unique identifier for the device |
| `video` | String (Base64) | **Required** | Base64-encoded video data |
| `timestamp` | ISO 8601 | Optional | Video timestamp (defaults to current time) |
| `metadata` | Object | Optional | Video metadata (duration, resolution, fps, etc.) |

#### Upload Video Data
Submit time-lapse garden video:

```bash
curl -X POST "${API_BASE_URL}/videos" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d '{
    "device_id": "garden-pi-003",
    "timestamp": "2024-08-21T10:00:00Z",
    "video": "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAA...",
    "metadata": {
      "duration_seconds": 300,
      "resolution": "1920x1080",
      "fps": 30
    }
  }'
```

### Count Endpoints

#### Get Resource Counts
Query counts for dashboard statistics:

```bash
# Get total classifications count
curl -G "${API_BASE_URL}/classifications/count" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}"

# Get device-specific detection count for last week
curl -G "${API_BASE_URL}/detections/count" \
  -H "X-API-Key: ${SENSING_GARDEN_API_KEY}" \
  -d device_id=garden-pi-001 \
  -d start_time=2024-08-14T00:00:00Z
```

### Response Examples

#### Successful Classification Response
```json
{
  "message": "Classification data stored successfully",
  "data": {
    "device_id": "garden-pi-001",
    "model_id": "yolov8n-insects-v1.2",
    "timestamp": "2024-08-21T14:30:00.000Z",
    "image_key": "classifications/garden-pi-001/2024-08-21-14-30-00.jpg",
    "image_bucket": "scl-sensing-garden-images",
    "family": "Apidae",
    "genus": "Apis",
    "species": "mellifera",
    "family_confidence": 0.92,
    "genus_confidence": 0.85,
    "species_confidence": 0.78,
    "location": {
      "lat": 40.7128,
      "long": -74.0060,
      "alt": 10.5
    },
    "temperature": 23.4,
    "humidity": 65.2,
    "pm1p0": 12.5,
    "pm2p5": 18.3,
    "pm4p0": 22.1,
    "pm10p0": 28.7,
    "voc_index": 150,
    "nox_index": 75
  }
}
```

#### Environmental Data Query Response
```json
{
  "readings": [
    {
      "device_id": "garden-pi-001",
      "timestamp": "2024-08-21T14:30:00Z",
      "temperature": 24.7,
      "humidity": 62.8,
      "pm1p0": 8.2,
      "pm2p5": 15.7,
      "pm4p0": 19.3,
      "pm10p0": 24.1,
      "voc_index": 135,
      "nox_index": 68,
      "location": {
        "lat": 40.7128,
        "long": -74.0060,
        "alt": 15.0
      }
    }
  ],
  "next_token": null,
  "count": 1
}
```

## Deployment

### Backend Deployment

The backend services (Lambda, API Gateway, etc.) are deployed using Terraform:

```bash
cd terraform
terraform init
terraform apply
```