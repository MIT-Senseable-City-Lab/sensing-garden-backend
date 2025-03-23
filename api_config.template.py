#!/usr/bin/env python3
"""
Template configuration for API endpoints in Sensing Garden Backend.

INSTRUCTIONS:
1. Copy this file to api_config.py (which is in .gitignore)
2. Replace placeholder values with your actual API credentials
3. NEVER commit your actual API credentials to the repository

This template provides the structure for the configuration without exposing
sensitive information in the repository.
"""
import os
from typing import Optional, Dict, Any

# Base URL for the API
DEFAULT_BASE_URL = "https://linyz44pd6.execute-api.us-east-1.amazonaws.com"
_base_url = None  # Module-level variable for the base URL

def get_base_url() -> str:
    """
    Get the base URL for API requests.
    
    Returns the base URL from environment variable or the default value
    if not set.
    
    Returns:
        Base URL for the API
    """
    global _base_url
    
    # If already set via set_base_url, use that value
    if _base_url is not None:
        return _base_url
        
    # Otherwise use environment variable or default
    return os.environ.get("API_BASE_URL", DEFAULT_BASE_URL)

def set_base_url(url: str) -> None:
    """
    Set the base URL for API requests. This is useful for testing.
    
    Args:
        url: Base URL for the API
    """
    global _base_url
    _base_url = url

def get_api_key() -> str:
    """
    Get the API key for authentication.
    
    Returns the API key from the environment variable or raises an error
    if not set.
    
    Returns:
        API key for authentication
        
    Raises:
        ValueError: If the API key is not set in environment variables
    """
    # REPLACE THIS: Get your API key and set as environment variable
    # For production, remove the default value and only use the env var
    api_key = os.environ.get("SENSING_GARDEN_API_KEY")
    
    if not api_key:
        raise ValueError(
            "SENSING_GARDEN_API_KEY environment variable is not set. "
            "Please set this variable to your API key."
        )
        
    return api_key

def get_auth_headers() -> Dict[str, str]:
    """
    Get the headers required for authentication.
    
    Returns:
        Dict containing the necessary headers for API authentication
    """
    return {
        "Content-Type": "application/json",
        "x-api-key": get_api_key()
    }
