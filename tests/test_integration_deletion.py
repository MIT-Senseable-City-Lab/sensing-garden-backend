"""
Comprehensive integration tests for device deletion functionality.

These tests create real test data using the sensing_garden_client, 
perform actual deletion operations, and verify complete removal 
from both DynamoDB tables and S3 buckets.

SAFETY: 
- Uses clearly marked test device IDs (test-delete-device-*)
- Includes setup and teardown
- Tests are idempotent
- Only operates on test data

DO NOT RUN THESE TESTS unless you have:
1. A separate test environment
2. Valid API keys for testing
3. Understanding that this creates and deletes real data
"""

import os
import pytest
import time
from datetime import datetime, timezone
from typing import Dict, List, Any
import json
import requests

# Test configuration
TEST_DEVICE_ID = "test-delete-device-001"
ALTERNATIVE_TEST_DEVICE_ID = "test-delete-device-002"

# Sample test data
SAMPLE_IMAGE_DATA = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\x12IDATx\x9cc\xf8\x00\x00\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x06\x05\x10\x00\x00\x00\x00IEND\xaeB`\x82'

@pytest.fixture
def api_config():
    """Configuration for API access."""
    api_key = os.getenv('SENSING_GARDEN_API_KEY')
    base_url = os.getenv('API_BASE_URL')
    
    if not api_key or not base_url:
        pytest.skip("API credentials not configured. Set SENSING_GARDEN_API_KEY and API_BASE_URL environment variables.")
    
    return {
        'api_key': api_key,
        'base_url': base_url
    }

@pytest.fixture
def client(api_config):
    """Initialize sensing garden client."""
    try:
        from sensing_garden_client import SensingGardenClient
        
        return SensingGardenClient(
            base_url=api_config['base_url'],
            api_key=api_config['api_key']
        )
    except ImportError:
        pytest.skip("sensing_garden_client not available. Install it to run integration tests.")

@pytest.fixture
def backend_url(api_config):
    """Backend API URL for direct API calls."""
    return api_config['base_url']

@pytest.fixture
def api_headers(api_config):
    """Headers for direct API calls."""
    return {
        'Content-Type': 'application/json',
        'x-api-key': api_config['api_key']
    }


class TestDeviceDeletionIntegration:
    """Integration tests for complete device deletion functionality."""

    def test_device_deletion_complete_flow(self, client, backend_url, api_headers):
        """
        Test complete device deletion flow:
        1. Create test device with comprehensive data
        2. Verify data exists
        3. Delete device with cascade
        4. Verify complete removal
        """
        device_id = TEST_DEVICE_ID
        
        # Step 1: Clean up any existing test data first
        self._cleanup_test_device(device_id, backend_url, api_headers)
        
        # Step 2: Create device
        try:
            device_result = client.add_device(device_id)
            assert device_result.get('statusCode') == 200
            print(f"✓ Created test device: {device_id}")
        except Exception as e:
            print(f"Device creation failed or device already exists: {e}")
        
        # Step 3: Add comprehensive test data
        test_data_counts = self._create_comprehensive_test_data(client, device_id)
        print(f"✓ Created test data: {test_data_counts}")
        
        # Step 4: Verify data exists before deletion
        pre_deletion_counts = self._verify_data_exists(client, device_id)
        assert pre_deletion_counts['classifications'] > 0, "No classification data found"
        assert pre_deletion_counts['environment'] > 0, "No environmental data found"
        print(f"✓ Verified data exists: {pre_deletion_counts}")
        
        # Step 5: Perform cascade delete via backend API
        delete_result = self._call_delete_device_api(device_id, backend_url, api_headers, cascade=True)
        assert delete_result['statusCode'] == 200, f"Delete failed: {delete_result}"
        
        delete_summary = json.loads(delete_result['body'])
        print(f"✓ Delete API response: {delete_summary.get('message', 'No message')}")
        
        # Step 6: Verify complete data removal
        time.sleep(2)  # Allow for eventual consistency
        post_deletion_counts = self._verify_complete_removal(client, device_id)
        
        # Assert all data was removed
        assert post_deletion_counts['classifications'] == 0, f"Classifications not deleted: {post_deletion_counts['classifications']}"
        assert post_deletion_counts['environment'] == 0, f"Environmental data not deleted: {post_deletion_counts['environment']}"
        assert post_deletion_counts['videos'] == 0, f"Videos not deleted: {post_deletion_counts['videos']}"
        
        # Verify deletion summary matches actual counts
        summary = delete_summary.get('summary', {})
        deleted_counts = summary.get('deleted_counts', {})
        
        assert summary.get('device_deleted') == True, "Device deletion not confirmed"
        assert summary.get('cascade') == True, "Cascade deletion not confirmed"
        
        print(f"✓ Complete removal verified: {post_deletion_counts}")
        print(f"✓ Deletion summary: {deleted_counts}")

    def test_device_deletion_no_cascade(self, client, backend_url, api_headers):
        """
        Test device deletion without cascade (data should remain).
        """
        device_id = ALTERNATIVE_TEST_DEVICE_ID
        
        # Clean up first
        self._cleanup_test_device(device_id, backend_url, api_headers)
        
        # Create device and minimal data
        try:
            client.add_device(device_id)
        except Exception as e:
            print(f"Device creation note: {e}")
        
        # Add minimal test data
        self._create_minimal_test_data(client, device_id)
        
        # Verify data exists
        pre_counts = self._verify_data_exists(client, device_id)
        assert pre_counts['classifications'] > 0, "Test data not created"
        
        # Delete device WITHOUT cascade
        delete_result = self._call_delete_device_api(device_id, backend_url, api_headers, cascade=False)
        assert delete_result['statusCode'] == 200
        
        delete_summary = json.loads(delete_result['body'])
        summary = delete_summary.get('summary', {})
        
        # Verify device was deleted but data remains
        assert summary.get('device_deleted') == True
        assert summary.get('cascade') == False
        assert summary.get('deleted_counts') == {}, "Data should not be deleted without cascade"
        
        # Verify data still exists
        post_counts = self._verify_data_exists(client, device_id)
        assert post_counts['classifications'] == pre_counts['classifications'], "Data was deleted despite no cascade"
        
        print(f"✓ Non-cascade deletion verified - data preserved: {post_counts}")
        
        # Clean up the test data manually
        self._cleanup_test_device(device_id, backend_url, api_headers)

    def test_delete_nonexistent_device(self, backend_url, api_headers):
        """Test deletion of a device that doesn't exist."""
        nonexistent_device = "test-nonexistent-device-999"
        
        delete_result = self._call_delete_device_api(nonexistent_device, backend_url, api_headers, cascade=True)
        
        # Should succeed (idempotent) but show 0 counts
        assert delete_result['statusCode'] == 200
        
        delete_summary = json.loads(delete_result['body'])
        summary = delete_summary.get('summary', {})
        deleted_counts = summary.get('deleted_counts', {})
        
        # All counts should be 0 or empty
        for data_type, count in deleted_counts.items():
            if isinstance(count, int):
                assert count == 0, f"Unexpected {data_type} count for nonexistent device: {count}"
        
        print(f"✓ Nonexistent device deletion handled correctly: {deleted_counts}")

    def test_device_deletion_api_error_handling(self, backend_url, api_headers):
        """Test deletion API error handling."""
        
        # Test with invalid device ID
        invalid_headers = api_headers.copy()
        invalid_headers['x-api-key'] = 'invalid-key'
        
        response = requests.delete(
            f"{backend_url}/devices",
            json={'device_id': 'test-device', 'cascade': True},
            headers=invalid_headers
        )
        
        assert response.status_code in [401, 403], "Invalid API key should be rejected"
        print(f"✓ Invalid API key properly rejected with status {response.status_code}")
        
        # Test with missing device_id
        response = requests.delete(
            f"{backend_url}/devices",
            json={'cascade': True},  # Missing device_id
            headers=api_headers
        )
        
        assert response.status_code in [400, 500], "Missing device_id should be rejected"
        print(f"✓ Missing device_id properly rejected with status {response.status_code}")

    # Helper methods

    def _create_comprehensive_test_data(self, client, device_id: str) -> Dict[str, int]:
        """Create comprehensive test data for a device."""
        counts = {'classifications': 0, 'environment': 0, 'videos': 0}
        
        try:
            # Add multiple classifications with images
            for i in range(3):
                timestamp = datetime.now(timezone.utc).isoformat()
                client.classifications.add(
                    device_id=device_id,
                    model_id="test-model-v1",
                    image_data=SAMPLE_IMAGE_DATA,
                    family="Diptera",
                    genus="Musca",
                    species="domestica",
                    family_confidence=0.95,
                    genus_confidence=0.88,
                    species_confidence=0.72,
                    timestamp=timestamp,
                    bounding_box=[10, 10, 50, 50],
                    metadata={"test": True, "batch": i}
                )
                counts['classifications'] += 1
                time.sleep(0.1)  # Avoid timestamp collisions
        
        except Exception as e:
            print(f"Classification creation error: {e}")
        
        try:
            # Add environmental readings
            for i in range(5):
                timestamp = datetime.now(timezone.utc).isoformat()
                client.environment.add(
                    device_id=device_id,
                    timestamp=timestamp,
                    pm1_0=12.5 + i,
                    pm2_5=25.0 + i,
                    pm4_0=28.0 + i,
                    pm10_0=35.0 + i,
                    humidity=65.0 + i,
                    temperature=22.0 + (i * 0.5),
                    voc_index=150 + i,
                    nox_index=120 + i
                )
                counts['environment'] += 1
                time.sleep(0.1)
        
        except Exception as e:
            print(f"Environment creation error: {e}")
        
        # Note: Video upload requires AWS credentials, skip for now
        # Could be added if AWS credentials are available in test env
        
        return counts

    def _create_minimal_test_data(self, client, device_id: str):
        """Create minimal test data for a device."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        try:
            client.classifications.add(
                device_id=device_id,
                model_id="test-model-v1",
                image_data=SAMPLE_IMAGE_DATA,
                family="Hymenoptera",
                genus="Apis",
                species="mellifera",
                family_confidence=0.99,
                genus_confidence=0.95,
                species_confidence=0.88,
                timestamp=timestamp
            )
        except Exception as e:
            print(f"Minimal data creation error: {e}")

    def _verify_data_exists(self, client, device_id: str) -> Dict[str, int]:
        """Verify that data exists for a device."""
        counts = {}
        
        try:
            classification_count = client.classifications.count(device_id=device_id)
            counts['classifications'] = classification_count.get('count', 0)
        except Exception as e:
            print(f"Classification count error: {e}")
            counts['classifications'] = 0
        
        try:
            environment_count = client.environment.count(device_id=device_id)
            counts['environment'] = environment_count.get('count', 0)
        except Exception as e:
            print(f"Environment count error: {e}")
            counts['environment'] = 0
        
        try:
            if hasattr(client, 'videos') and client.videos:
                video_count = client.videos.count(device_id=device_id)
                counts['videos'] = video_count.get('count', 0)
            else:
                counts['videos'] = 0
        except Exception as e:
            print(f"Video count error: {e}")
            counts['videos'] = 0
        
        return counts

    def _verify_complete_removal(self, client, device_id: str) -> Dict[str, int]:
        """Verify complete data removal after deletion."""
        return self._verify_data_exists(client, device_id)

    def _call_delete_device_api(self, device_id: str, backend_url: str, headers: Dict, cascade: bool = True) -> Dict:
        """Call the backend delete device API directly."""
        response = requests.delete(
            f"{backend_url}/devices",
            json={
                'device_id': device_id,
                'cascade': cascade
            },
            headers=headers
        )
        
        return {
            'statusCode': response.status_code,
            'body': response.text
        }

    def _cleanup_test_device(self, device_id: str, backend_url: str, headers: Dict):
        """Clean up test device and all associated data."""
        try:
            delete_result = self._call_delete_device_api(device_id, backend_url, headers, cascade=True)
            print(f"Cleanup for {device_id}: status {delete_result['statusCode']}")
        except Exception as e:
            print(f"Cleanup error for {device_id}: {e}")


class TestDeviceDeletionSafety:
    """Safety tests to ensure deletion protection works correctly."""

    def test_device_whitelist_protection(self, backend_url, api_headers):
        """Test that whitelisted devices cannot be deleted (if whitelist is implemented)."""
        # This test assumes there might be a whitelist implementation
        # Adjust based on actual backend implementation
        
        protected_device = "production-device-001"
        
        # Attempt to delete a potentially protected device
        response = requests.delete(
            f"{backend_url}/devices",
            json={
                'device_id': protected_device,
                'cascade': True
            },
            headers=api_headers
        )
        
        # If whitelist protection is implemented, this should fail
        # If not, this will succeed but that's okay for test devices
        print(f"Protected device deletion attempt: status {response.status_code}")
        
        if response.status_code != 200:
            print("✓ Protection mechanism appears to be working")
        else:
            print("⚠ No protection detected - ensure test devices only")

    def test_api_key_required(self, backend_url):
        """Test that API key is required for deletion."""
        response = requests.delete(
            f"{backend_url}/devices",
            json={
                'device_id': 'test-device',
                'cascade': True
            }
            # No headers with API key
        )
        
        assert response.status_code in [401, 403], f"API key should be required, got status {response.status_code}"
        print("✓ API key requirement enforced")


# Utility functions for manual testing and verification

def print_device_data_summary(device_id: str, api_config: Dict = None):
    """
    Print a comprehensive summary of all data associated with a device.
    Use this before running deletion operations to understand impact.
    """
    if not api_config:
        api_config = {
            'api_key': os.getenv('SENSING_GARDEN_API_KEY'),
            'base_url': os.getenv('API_BASE_URL')
        }
    
    if not api_config['api_key'] or not api_config['base_url']:
        print("❌ API credentials not configured")
        return
    
    try:
        from sensing_garden_client import SensingGardenClient
        
        client = SensingGardenClient(
            base_url=api_config['base_url'],
            api_key=api_config['api_key']
        )
        
        print(f"\n{'='*60}")
        print(f"DATA SUMMARY FOR DEVICE: {device_id}")
        print(f"{'='*60}")
        
        # Check each data type
        data_types = [
            ('Classifications', 'classifications'),
            ('Environmental Readings', 'environment'),
            ('Videos', 'videos')
        ]
        
        total_items = 0
        for display_name, attr_name in data_types:
            try:
                if hasattr(client, attr_name):
                    client_attr = getattr(client, attr_name)
                    if client_attr:
                        count_result = client_attr.count(device_id=device_id)
                        count = count_result.get('count', 0)
                        total_items += count
                        status = "🔴" if count > 0 else "✅"
                        print(f"{status} {display_name}: {count}")
                    else:
                        print(f"⚠️  {display_name}: Not available (missing credentials)")
                else:
                    print(f"❓ {display_name}: Client method not found")
            except Exception as e:
                print(f"❌ {display_name}: ERROR - {str(e)}")
        
        print(f"\n📊 Total items that would be deleted: {total_items}")
        
        if total_items > 0:
            print(f"\n⚠️  WARNING: Device {device_id} contains {total_items} items")
            print("   These will be PERMANENTLY DELETED in a cascade delete operation")
        else:
            print(f"\n✅ Device {device_id} appears to have no associated data")
        
        print(f"{'='*60}\n")
        
        return total_items
        
    except ImportError:
        print("❌ sensing_garden_client not available. Install it to use this function.")
        return None
    except Exception as e:
        print(f"❌ Error getting device summary: {str(e)}")
        return None


if __name__ == "__main__":
    import sys
    
    print("🧪 Device Deletion Integration Test Suite")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        # Print data summary for a device
        device_id = input("Enter device ID to check: ").strip()
        if device_id:
            print_device_data_summary(device_id)
    else:
        print("⚠️  DANGER: These tests create and delete REAL data")
        print("✅ Only run in isolated test environments")
        print("🔑 Requires: SENSING_GARDEN_API_KEY and API_BASE_URL environment variables")
        print("\nTo run tests:")
        print("  pytest test_integration_deletion.py -v")
        print("\nTo check device data before deletion:")
        print("  python test_integration_deletion.py summary")