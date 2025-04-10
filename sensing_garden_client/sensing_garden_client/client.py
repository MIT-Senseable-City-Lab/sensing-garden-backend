"""
Core client for Sensing Garden API interactions.
Provides base functionality used by all endpoint modules and the main client class.
"""
from typing import Dict, Any, Mapping, Optional
import requests

# Import sub-clients - these imports will be resolved when the package is fully loaded
# to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .models import ModelsClient
    from .detections import DetectionsClient
    from .classifications import ClassificationsClient
    from .videos import VideosClient


class BaseClient:
    """Base client for API interactions. Used internally by the feature-specific clients."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize the Base API client.
        
        Args:
            base_url: Base URL for the API without trailing slash
            api_key: API key for authenticated endpoints (required for POST operations)
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        
    def get(self, endpoint: str, params: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        """
        Make a GET request to the API.
        
        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
            
        Returns:
            API response as dictionary
        
        Raises:
            ValueError: If base_url is not set
            requests.HTTPError: For HTTP error responses
        """
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a POST request to the API.
        
        Args:
            endpoint: API endpoint (without base URL)
            payload: Request payload data
            
        Returns:
            API response as dictionary
            
        Raises:
            ValueError: If base_url or api_key is not set
            requests.HTTPError: For HTTP error responses
        """
        if not self.api_key:
            raise ValueError("API key is required for POST operations")
            
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


class SensingGardenClient:
    """Main client for interacting with the Sensing Garden API."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize the Sensing Garden API client with domain-specific sub-clients.
        
        Args:
            base_url: Base URL for the API without trailing slash
            api_key: API key for authenticated endpoints (required for POST operations)
        """
        self._base_client = BaseClient(base_url, api_key)
        
        # Initialize domain-specific clients
        from .models import ModelsClient
        from .detections import DetectionsClient
        from .classifications import ClassificationsClient
        from .videos import VideosClient
        
        self.models = ModelsClient(self._base_client)
        self.detections = DetectionsClient(self._base_client)
        self.classifications = ClassificationsClient(self._base_client)
        self.videos = VideosClient(self._base_client)
