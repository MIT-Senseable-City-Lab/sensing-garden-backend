"""
Example usage of the new sensing_garden_client API structure.

This script demonstrates how to use the new object-oriented API client.
"""
import os
from datetime import datetime
import sensing_garden_client

# Load API credentials from environment variables
api_key = os.environ.get("SENSING_GARDEN_API_KEY")
api_base_url = os.environ.get("API_BASE_URL")

# Initialize the client
sgc = sensing_garden_client.SensingGardenClient(api_base_url, api_key)

# Examples of using the models client
print("=== Models API ===")
try:
    # Create a model
    model_result = sgc.models.create(
        model_id="example-model-123",
        name="Example Model",
        version="1.0.0",
        description="A model created using the new client API"
    )
    print(f"Created model: {model_result}")
    
    # Fetch models
    models = sgc.models.fetch(limit=5)
    print(f"Retrieved {len(models.get('items', []))} models")
except Exception as e:
    print(f"Error with models API: {str(e)}")

# Examples of using the detections client (commented out as it requires image data)
print("\n=== Detections API ===")
"""
# To use this example, uncomment and provide actual image data
with open("example_image.jpg", "rb") as f:
    image_data = f.read()

# Add a detection
detection_result = sgc.detections.add(
    device_id="device-123",
    model_id="example-model-123",
    image_data=image_data,
    bounding_box=[0.1, 0.2, 0.3, 0.4],
    timestamp=datetime.utcnow().isoformat()
)
print(f"Created detection: {detection_result}")
"""

# Fetch detections
try:
    detections = sgc.detections.fetch(limit=5)
    print(f"Retrieved {len(detections.get('items', []))} detections")
except Exception as e:
    print(f"Error with detections API: {str(e)}")

# Examples of using the classifications client (commented out as it requires image data)
print("\n=== Classifications API ===")
"""
# To use this example, uncomment and provide actual image data
with open("example_image.jpg", "rb") as f:
    image_data = f.read()

# Add a classification
classification_result = sgc.classifications.add(
    device_id="device-123",
    model_id="example-model-123",
    image_data=image_data,
    family="Rosaceae",
    genus="Rosa",
    species="Rosa gallica",
    family_confidence=0.95,
    genus_confidence=0.92,
    species_confidence=0.85,
    timestamp=datetime.utcnow().isoformat()
)
print(f"Created classification: {classification_result}")
"""

# Fetch classifications
try:
    classifications = sgc.classifications.fetch(limit=5)
    print(f"Retrieved {len(classifications.get('items', []))} classifications")
except Exception as e:
    print(f"Error with classifications API: {str(e)}")
