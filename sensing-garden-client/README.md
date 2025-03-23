# Sensing Garden Client

A Python client for interacting with the Sensing Garden API.

## Installation

```bash
pip install sensing-garden-client
```

## Usage

```python
from sensing_garden_client import SensingGardenClient, get_models, send_classification_request

# Initialize the client
client = SensingGardenClient(
    base_url="https://api.example.com", 
    api_key="your-api-key"  # Only needed for POST operations
)

# Example: Get models
models = get_models(
    client=client,
    device_id="device-123",
    limit=10
)

# Example: Send a classification request
with open("plant_image.jpg", "rb") as f:
    image_data = f.read()

response = send_classification_request(
    client=client,
    device_id="device-123",
    model_id="model-456",
    image_data=image_data,
    family="Rosaceae",
    genus="Rosa",
    species="Rosa gallica",
    family_confidence=0.95,
    genus_confidence=0.92,
    species_confidence=0.89,
    timestamp="2023-06-01T12:34:56Z"
)
```

## Features

- GET operations for models, detections, and classifications
- POST operations for submitting detections and classifications
- Model management operations

## Dependencies

- `requests`: For API communication
