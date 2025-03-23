"""
Sensing Garden Client

A Python client for interacting with the Sensing Garden API.
"""

__version__ = "0.0.2"

from .client import SensingGardenClient

# All functionality is now provided through the SensingGardenClient class

__all__ = [
    # Main entry point for the API
    'SensingGardenClient',
]
