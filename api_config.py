#!/usr/bin/env python3
"""
Configuration for API endpoints in Sensing Garden Backend.

This module centralizes configuration for the API client modules, including
handling of authentication and URLs in a secure manner.

SECURITY NOTE:
    This file does NOT contain actual API keys, but instead loads them from environment
    variables. API keys should never be committed to the repository.

Setting up credentials:
    1. Create a .env file in the project root with the following content:
       ```
       SENSING_GARDEN_API_KEY=your_api_key_here
       API_BASE_URL=https://your-api-endpoint.execute-api.region.amazonaws.com
       ```
    2. Make sure .env is in your .gitignore file (it already is)
    3. Alternatively, set these variables directly in your environment
"""
import os
from typing import Optional, Dict, Any

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file if it exists
except ImportError:
    pass  # dotenv is not required, just a convenience

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
    Get the API key for authentication from environment variables.
    
    This function retrieves the API key from the SENSING_GARDEN_API_KEY
    environment variable. For development, use a .env file to set this variable.
    
    Returns:
        API key for authentication
        
    Raises:
        ValueError: If the API key is not set in the environment
    """
    api_key = os.environ.get("SENSING_GARDEN_API_KEY")
    
    if not api_key:
        raise ValueError(
            "SENSING_GARDEN_API_KEY environment variable is not set. "
            "Please create a .env file with your API key or set it in your environment."
        )
        
    return api_key

def get_auth_headers() -> dict:
    """
    Get the headers required for authentication.
    
    Returns:
        Dictionary of headers including the API key
        
    Raises:
        ValueError: If the API key is not set in environment variables
    """
    return {
        "Content-Type": "application/json",
        "x-api-key": get_api_key()
    }
