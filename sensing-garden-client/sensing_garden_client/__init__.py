"""
Sensing Garden Client

A Python client for interacting with the Sensing Garden API.
"""

__version__ = "0.1.0"

from .client import SensingGardenClient
from .get_endpoints import get_models, get_detections, get_classifications
from .post_endpoints import send_detection_request, send_classification_request
from .model_endpoints import send_model_request

__all__ = [
    'SensingGardenClient',
    'get_models',
    'get_detections',
    'get_classifications',
    'send_detection_request',
    'send_classification_request',
    'send_model_request',
]
