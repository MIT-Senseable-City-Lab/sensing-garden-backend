#!/usr/bin/env python3
"""
Test for submitting a classification using data from a JSON object, with supplied device_id and model_id.
"""
import os
import json
import base64
from typing import Dict, Any

import pytest
from .test_utils import get_client, create_test_image

@pytest.mark.parametrize("device_id,model_id,json_path,image_field", [
    ("test-device-json", "test-model-json", "tests/data/detection_results_20250425_145518.json", "frame_0158.jpg"),
])
def test_classification_from_json(device_id, model_id, json_path, image_field):
    """
    Loads a sample detection/classification dict from a JSON file and submits it as a classification using the client.
    """
    # Load JSON data
    with open(json_path, "r") as f:
        data = json.load(f)
    sample = data[image_field][0]

    # Prepare image data (use a generated test image)
    image_data = create_test_image()

    # Map bbox to bounding_box if present
    bounding_box = sample.get("bbox") or sample.get("bounding_box")
    
    # Compose classification payload
    payload = dict(
        device_id=device_id,
        model_id=model_id,
        image_data=image_data,
        family=sample["family"],
        genus=sample["genus"],
        species=sample["species"],
        family_confidence=sample["family_confidence"],
        genus_confidence=sample["genus_confidence"],
        species_confidence=sample["species_confidence"],
        timestamp=sample.get("timestamp"),
    )
    if bounding_box:
        payload["bounding_box"] = bounding_box

    client = get_client()
    response = client.classifications.add(**payload)
    print("Response:", response)
    assert response, "No response from API"
    if bounding_box:
        # Check that bounding_box is echoed back
        returned_box = response.get("bounding_box")
        if not returned_box and isinstance(response, dict) and "data" in response:
            returned_box = response["data"].get("bounding_box")
        assert returned_box == bounding_box, f"bounding_box mismatch: {returned_box} != {bounding_box}"
