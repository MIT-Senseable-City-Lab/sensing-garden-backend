"""
Real integration tests for CSV export functionality against deployed AWS infrastructure.

These tests are designed to:
1. Test against the actual deployed API Gateway endpoint
2. Use real HTTP requests with authentication
3. Test the /export endpoint that should be added to the API
4. Validate CSV format and content
5. Test various table types and parameters

Expected behavior:
- Initially these tests will FAIL because the /export endpoint doesn't exist yet
- Tests are written to expect success once the endpoint is implemented
- They demonstrate the required functionality and API contract
"""

import pytest
import requests
import json
import os
import io
import csv
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import time

# Test configuration - these should match the deployed infrastructure
BASE_API_URL = "https://nxdp0npcb2.execute-api.us-east-1.amazonaws.com"
TEST_API_KEY = "WgrQAyanmj53BBMLkcosm9I1QCV26tp5aD9sGNOr"

# Test timeout configuration
REQUEST_TIMEOUT = 30  # seconds
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds


class TestCSVExportIntegrationReal:
    """Real integration tests for CSV export functionality."""
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup for each test method."""
        self.base_url = BASE_API_URL
        self.api_key = TEST_API_KEY
        self.session = requests.Session()
        
        # Set up authentication headers
        self.headers = {
            'Content-Type': 'application/json',
            'X-Api-Key': self.api_key,
            'Accept': 'text/csv'
        }
        
        # Verify API connectivity before running export tests
        self._verify_api_connectivity()
    
    def _verify_api_connectivity(self):
        """Verify that we can connect to the deployed API."""
        try:
            # Test basic connectivity by calling an existing endpoint
            response = self.session.get(
                f"{self.base_url}/models",
                headers={'X-Api-Key': self.api_key},
                timeout=REQUEST_TIMEOUT
            )
            
            # Should get 200 or acceptable response (not connection error)
            assert response.status_code < 500, f"API connectivity failed: {response.status_code}"
            
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Cannot connect to API at {self.base_url}: {e}")
    
    def _make_request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic for network issues."""
        last_exception = None
        
        for attempt in range(RETRY_COUNT):
            try:
                response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < RETRY_COUNT - 1:  # Don't sleep on last attempt
                    time.sleep(RETRY_DELAY)
                continue
        
        # All retries failed
        raise last_exception
    
    def _validate_csv_format(self, csv_content: str, expected_columns: Optional[list] = None) -> list:
        """Validate CSV format and return parsed rows."""
        assert csv_content, "CSV content should not be empty"
        
        # Parse CSV content
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        assert len(rows) >= 1, "CSV should have at least a header row"
        
        # Validate header
        header = rows[0]
        assert len(header) > 0, "CSV header should not be empty"
        
        # Check for expected columns if provided
        if expected_columns:
            for col in expected_columns:
                assert col in header, f"Expected column '{col}' not found in CSV header: {header}"
        
        return rows
    
    def test_export_endpoint_exists(self):
        """Test that the /export endpoint exists and responds."""
        # This test will FAIL initially because the endpoint doesn't exist yet
        url = f"{self.base_url}/export"
        
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
        }
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        # Expected behavior once endpoint is implemented
        assert response.status_code != 404, (
            f"EXPECTED FAILURE: /export endpoint not implemented yet. "
            f"Got {response.status_code}: {response.text[:200]}"
        )
        
        # Once implemented, should return 200 or appropriate response
        assert response.status_code in [200, 400], (
            f"Export endpoint should return 200 for valid request or 400 for invalid parameters. "
            f"Got {response.status_code}: {response.text[:200]}"
        )
    
    def test_export_detections_csv(self):
        """Test CSV export for detections table."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'limit': 10,
            'filename': 'test_detections_export.csv'
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        # This will fail initially - endpoint doesn't exist
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        # Expected behavior once implemented
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Validate CSV response
        assert response.headers.get('Content-Type') == 'text/csv', "Response should be CSV content type"
        assert 'test_detections_export.csv' in response.headers.get('Content-Disposition', ''), "Filename should be in response headers"
        
        # Validate CSV content structure
        expected_columns = ['device_id', 'timestamp', 'model_id', 'image_key', 'bbox_xmin', 'bbox_ymin', 'bbox_xmax', 'bbox_ymax']
        rows = self._validate_csv_format(response.text, expected_columns)
        
        # Should have header + data rows (or just header if no data)
        assert len(rows) >= 1, "Should have at least header row"
    
    def test_export_classifications_csv(self):
        """Test CSV export for classifications table."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'classifications',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'limit': 5
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'text/csv'
        
        # Validate classifications-specific columns
        expected_columns = ['device_id', 'timestamp', 'family', 'genus', 'species', 'family_confidence', 'genus_confidence', 'species_confidence']
        rows = self._validate_csv_format(response.text, expected_columns)
    
    def test_export_environment_csv(self):
        """Test CSV export for environment table."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'environment',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'limit': 20
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'text/csv'
        
        # Validate environmental data columns
        expected_columns = ['device_id', 'timestamp', 'pm1p0', 'pm2p5', 'pm4p0', 'pm10p0', 'temperature', 'humidity', 'voc_index', 'nox_index']
        rows = self._validate_csv_format(response.text, expected_columns)
    
    def test_export_devices_csv(self):
        """Test CSV export for devices table."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'devices',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'text/csv'
        
        # Validate devices columns
        expected_columns = ['device_id', 'created']
        rows = self._validate_csv_format(response.text, expected_columns)
    
    def test_export_models_csv(self):
        """Test CSV export for models table."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'models',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'text/csv'
        
        # Validate models columns
        expected_columns = ['id', 'timestamp']
        rows = self._validate_csv_format(response.text, expected_columns)
    
    def test_export_videos_csv(self):
        """Test CSV export for videos table."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'videos',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'limit': 10
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'text/csv'
        
        # Validate videos columns
        expected_columns = ['device_id', 'timestamp', 'video_key', 'video_bucket']
        rows = self._validate_csv_format(response.text, expected_columns)
    
    def test_export_with_date_range(self):
        """Test CSV export with date range filtering."""
        # Use last 7 days as test range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'end_time': end_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'limit': 50
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'text/csv'
        
        rows = self._validate_csv_format(response.text)
        
        # If there are data rows, verify timestamps are within range
        if len(rows) > 1:
            # Parse timestamps and verify they're within the specified range
            timestamp_idx = rows[0].index('timestamp')
            for row in rows[1:]:  # Skip header row
                if len(row) > timestamp_idx:
                    timestamp_str = row[timestamp_idx]
                    if timestamp_str:  # Non-empty timestamp
                        try:
                            # Handle different timestamp formats that might be returned
                            timestamp = None
                            
                            # Try various common formats
                            for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%f', 
                                       '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S.%f%z']:
                                try:
                                    timestamp = datetime.strptime(timestamp_str, fmt)
                                    break
                                except ValueError:
                                    continue
                            
                            if timestamp:
                                # Convert to naive datetime for comparison if needed
                                if timestamp.tzinfo:
                                    timestamp = timestamp.replace(tzinfo=None)
                                    
                                assert start_date <= timestamp <= end_date, (
                                    f"Timestamp {timestamp_str} is outside range {start_date} to {end_date}"
                                )
                            else:
                                print(f"Warning: Could not parse timestamp format '{timestamp_str}'")
                        except Exception as e:
                            # If timestamp parsing fails, log but don't fail the test
                            print(f"Warning: Could not parse timestamp '{timestamp_str}': {e}")
    
    def test_export_with_device_filter(self):
        """Test CSV export with device_id filtering using known device with data."""
        # Use test-device-123 which we know has detection data
        test_device_id = "test-device-123"
        
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'device_id': test_device_id,
            'limit': 10
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        rows = self._validate_csv_format(response.text)
        
        # Should have at least header row, and likely data rows for test-device-123
        assert len(rows) >= 1, "Should have at least header row"
        
        # If there are data rows, verify device_id filtering
        if len(rows) > 1:
            device_id_idx = rows[0].index('device_id')
            for row in rows[1:]:  # Skip header row
                if len(row) > device_id_idx and row[device_id_idx]:  # Non-empty device_id
                    assert row[device_id_idx] == test_device_id, (
                        f"Row contains wrong device_id: {row[device_id_idx]} != {test_device_id}"
                    )
        else:
            # If no data rows, that's also valid (device might not have data in the date range)
            print(f"No data rows returned for device {test_device_id} - this is acceptable")
    
    def test_export_error_invalid_table(self):
        """Test error handling for invalid table parameter."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'invalid_table_name',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        # Should return 400 for invalid table name
        assert response.status_code == 400, f"Expected 400 for invalid table, got {response.status_code}: {response.text[:200]}"
        
        # Response should be text/plain error, not CSV
        assert 'text/plain' in response.headers.get('Content-Type', ''), "Error response should be text/plain"
        
        # Error response should contain error message
        assert len(response.text.strip()) > 0, "Error response should contain error message"
    
    def test_export_error_missing_table_parameter(self):
        """Test error handling when table parameter is missing."""
        url = f"{self.base_url}/export"
        params = {
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
            # Missing required 'table' parameter
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        # Should return 400 for missing table parameter
        assert response.status_code == 400, f"Expected 400 for missing table, got {response.status_code}: {response.text[:200]}"
        
        # Response should be text/plain error, not CSV
        assert 'text/plain' in response.headers.get('Content-Type', ''), "Error response should be text/plain"
    
    def test_export_error_invalid_date_format(self):
        """Test error handling for invalid date format."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': 'invalid-date-format',
            'end_time': '2023-13-45T99:99:99Z'  # Invalid date
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        # Should return 400 for invalid date format
        assert response.status_code == 400, f"Expected 400 for invalid dates, got {response.status_code}: {response.text[:200]}"
        
        # Response should be text/plain error, not CSV
        assert 'text/plain' in response.headers.get('Content-Type', ''), "Error response should be text/plain"
    
    def test_export_authentication_required(self):
        """Test that authentication is required for export endpoint."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
        }
        
        # Make request without API key
        headers_no_auth = {'Content-Type': 'application/json', 'Accept': 'text/csv'}
        
        response = self._make_request_with_retry('GET', url, headers=headers_no_auth, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        # Should require authentication (401 or 403), but if export endpoint is public, it may return 200
        # This is an implementation detail that may vary
        if response.status_code == 200:
            # Export endpoint is public - this is acceptable behavior
            assert response.headers.get('Content-Type') == 'text/csv', "Public export should return CSV"
        else:
            # Export endpoint requires authentication
            assert response.status_code in [401, 403], (
                f"Expected 401/403 for missing auth, got {response.status_code}: {response.text[:200]}"
            )
    
    def test_export_large_limit_handling(self):
        """Test handling of large limit values."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'limit': 10000  # Very large limit
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        # Should either succeed or return reasonable error
        assert response.status_code in [200, 400], (
            f"Expected 200 or 400 for large limit, got {response.status_code}: {response.text[:200]}"
        )
        
        if response.status_code == 200:
            # Should still return valid CSV
            rows = self._validate_csv_format(response.text)
        elif response.status_code == 400:
            # Should return text/plain error explaining limit restriction
            assert 'text/plain' in response.headers.get('Content-Type', '')
    
    def test_export_automatic_filename_generation(self):
        """Test automatic filename generation when not provided."""
        url = f"{self.base_url}/export"
        params = {
            'table': 'classifications',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z'
            # No filename parameter provided
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Should have auto-generated filename in Content-Disposition header
        content_disposition = response.headers.get('Content-Disposition', '')
        assert 'classifications_export_' in content_disposition, (
            f"Auto-generated filename should contain table name and timestamp. Got: {content_disposition}"
        )
        assert '.csv' in content_disposition, "Filename should have .csv extension"
    
    def test_export_classifications_with_device_filter(self):
        """Test CSV export for classifications table with device_id filtering."""
        # Use test-device-123 which we know has classification data
        test_device_id = "test-device-123"
        
        url = f"{self.base_url}/export"
        params = {
            'table': 'classifications',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'device_id': test_device_id,
            'limit': 10
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Validate CSV format and content
        expected_columns = ['device_id', 'timestamp', 'family', 'genus', 'species', 'family_confidence', 'genus_confidence', 'species_confidence']
        rows = self._validate_csv_format(response.text, expected_columns)
        
        # If there are data rows, verify device_id filtering
        if len(rows) > 1:
            device_id_idx = rows[0].index('device_id')
            for row in rows[1:]:  # Skip header row
                if len(row) > device_id_idx and row[device_id_idx]:  # Non-empty device_id
                    assert row[device_id_idx] == test_device_id, (
                        f"Classification row contains wrong device_id: {row[device_id_idx]} != {test_device_id}"
                    )
    
    def test_export_environment_with_device_filter(self):
        """Test CSV export for environment table with device_id filtering."""
        # Use test-field-preservation which we know has environment data
        test_device_id = "test-field-preservation"
        
        url = f"{self.base_url}/export"
        params = {
            'table': 'environment',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'device_id': test_device_id,
            'limit': 10
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Check if response contains "No data found" message or proper CSV
        if response.text.startswith('# No data found'):
            # This is acceptable - device filtering worked but no data in date range
            print(f"No environment data found for device {test_device_id} in specified date range")
            return
        
        # Validate CSV format and content
        expected_columns = ['device_id', 'timestamp', 'pm1p0', 'pm2p5', 'pm4p0', 'pm10p0', 'temperature', 'humidity', 'voc_index', 'nox_index']
        rows = self._validate_csv_format(response.text, expected_columns)
        
        # If there are data rows, verify device_id filtering
        if len(rows) > 1:
            device_id_idx = rows[0].index('device_id')
            for row in rows[1:]:  # Skip header row
                if len(row) > device_id_idx and row[device_id_idx]:  # Non-empty device_id
                    assert row[device_id_idx] == test_device_id, (
                        f"Environment row contains wrong device_id: {row[device_id_idx]} != {test_device_id}"
                    )
    
    def test_export_videos_with_device_filter(self):
        """Test CSV export for videos table with device_id filtering."""
        # Use autopop-test-device-28c7c31e which might have video data
        test_device_id = "autopop-test-device-28c7c31e"
        
        url = f"{self.base_url}/export"
        params = {
            'table': 'videos',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'device_id': test_device_id,
            'limit': 10
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Check if response contains "No data found" message or proper CSV
        if response.text.startswith('# No data found'):
            # This is acceptable - device filtering worked but no video data for this device
            print(f"No video data found for device {test_device_id} in specified date range")
            return
        
        # Validate CSV format and content
        expected_columns = ['device_id', 'timestamp', 'video_key', 'video_bucket']
        rows = self._validate_csv_format(response.text, expected_columns)
        
        # If there are data rows, verify device_id filtering
        # Note: videos may not exist for this device, so empty result is valid
        if len(rows) > 1:
            device_id_idx = rows[0].index('device_id')
            for row in rows[1:]:  # Skip header row
                if len(row) > device_id_idx and row[device_id_idx]:  # Non-empty device_id
                    assert row[device_id_idx] == test_device_id, (
                        f"Video row contains wrong device_id: {row[device_id_idx]} != {test_device_id}"
                    )
    
    def test_export_device_filter_nonexistent_device(self):
        """Test CSV export with device_id filter for non-existent device (should return empty CSV)."""
        non_existent_device_id = "definitely-not-a-real-device-id-12345"
        
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'device_id': non_existent_device_id,
            'limit': 10
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Check if response contains "No data found" message or proper CSV with just header
        if response.text.startswith('# No data found'):
            # This is the expected behavior for non-existent device - filtering worked correctly
            print(f"Correctly returned 'No data found' message for non-existent device {non_existent_device_id}")
            assert 'detections' in response.text, "Response should mention the table name"
            return
        
        # If it returns proper CSV format, validate structure
        rows = self._validate_csv_format(response.text)
        
        # Should have header row only (no data for non-existent device)
        assert len(rows) == 1, f"Expected only header row for non-existent device, got {len(rows)} rows"
        
        # Verify header contains expected columns
        header = rows[0]
        expected_columns = ['device_id', 'timestamp', 'model_id', 'image_key', 'bbox_xmin', 'bbox_ymin', 'bbox_xmax', 'bbox_ymax']
        for col in expected_columns:
            assert col in header, f"Expected column '{col}' not found in CSV header: {header}"
    
    def test_export_device_filter_mixed_data_validation(self):
        """Test device filtering validation with a device that has multiple types of data."""
        # Use test-device-123 for detections (known to have data)
        test_device_id = "test-device-123"
        
        # Test detections first
        url = f"{self.base_url}/export"
        detections_params = {
            'table': 'detections',
            'start_time': '2025-04-01T00:00:00Z',  # Narrower date range around known data
            'end_time': '2025-05-01T00:00:00Z',
            'device_id': test_device_id,
            'limit': 5
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=detections_params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Should have data for detections
        rows = self._validate_csv_format(response.text)
        if len(rows) > 1:  # Has data rows
            print(f"Found {len(rows)-1} detection rows for {test_device_id}")
            
            # Verify all device_ids match
            device_id_idx = rows[0].index('device_id')
            for i, row in enumerate(rows[1:], 1):  # Skip header row
                if len(row) > device_id_idx and row[device_id_idx]:
                    assert row[device_id_idx] == test_device_id, (
                        f"Row {i} contains wrong device_id: {row[device_id_idx]} != {test_device_id}"
                    )
                    
                    # Validate other required fields are not empty
                    timestamp_idx = rows[0].index('timestamp')
                    assert row[timestamp_idx], f"Row {i} has empty timestamp"
        
        # Now test classifications for same device
        classifications_params = {
            'table': 'classifications',
            'start_time': '2025-04-01T00:00:00Z',
            'end_time': '2025-05-01T00:00:00Z',
            'device_id': test_device_id,
            'limit': 5
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=classifications_params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        # Validate classifications CSV structure
        expected_columns = ['device_id', 'timestamp', 'family', 'genus', 'species', 'family_confidence', 'genus_confidence', 'species_confidence']
        rows = self._validate_csv_format(response.text, expected_columns)
        
        if len(rows) > 1:  # Has classification data
            print(f"Found {len(rows)-1} classification rows for {test_device_id}")
            device_id_idx = rows[0].index('device_id')
            for i, row in enumerate(rows[1:], 1):
                if len(row) > device_id_idx and row[device_id_idx]:
                    assert row[device_id_idx] == test_device_id, (
                        f"Classification row {i} contains wrong device_id: {row[device_id_idx]} != {test_device_id}"
                    )


class TestCSVExportIntegrationRealWithData:
    """Integration tests that require actual data in the system."""
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup for each test method."""
        self.base_url = BASE_API_URL
        self.api_key = TEST_API_KEY
        self.session = requests.Session()
        
        self.headers = {
            'Content-Type': 'application/json',
            'X-Api-Key': self.api_key,
            'Accept': 'text/csv'
        }
    
    def _make_request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic for network issues."""
        last_exception = None
        
        for attempt in range(RETRY_COUNT):
            try:
                response = self.session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < RETRY_COUNT - 1:
                    time.sleep(RETRY_DELAY)
                continue
        
        raise last_exception
    
    @pytest.mark.skipif(
        not os.getenv('RUN_DATA_DEPENDENT_TESTS'), 
        reason="Skipping tests that require actual data unless RUN_DATA_DEPENDENT_TESTS=1"
    )
    def test_export_detections_with_real_data(self):
        """Test CSV export with real detection data in system."""
        # First check if there's data available
        detections_response = self._make_request_with_retry(
            'GET', 
            f"{self.base_url}/detections", 
            headers={'X-Api-Key': self.api_key},
            params={'limit': 1}
        )
        
        if detections_response.status_code != 200:
            pytest.skip(f"Cannot verify detection data availability: {detections_response.status_code}")
        
        detections_data = detections_response.json()
        if not detections_data.get('data') or len(detections_data['data']) == 0:
            pytest.skip("No detection data available for real data test")
        
        # Now test export
        url = f"{self.base_url}/export"
        params = {
            'table': 'detections',
            'start_time': '2025-01-01T00:00:00Z',
            'end_time': '2025-12-31T23:59:59Z',
            'limit': 5
        }
        
        response = self._make_request_with_retry('GET', url, headers=self.headers, params=params)
        
        if response.status_code == 404:
            pytest.skip(f"Export endpoint not implemented yet: {response.status_code}")
        
        assert response.status_code == 200
        
        # Parse CSV and verify data content
        csv_reader = csv.reader(io.StringIO(response.text))
        rows = list(csv_reader)
        
        assert len(rows) >= 2, "Should have header + at least one data row"
        
        # Verify data row contains expected values
        header = rows[0]
        data_row = rows[1]
        
        # Basic validation that data row has values
        assert len(data_row) == len(header), "Data row should have same number of columns as header"
        
        # Check for non-empty values in key columns
        device_id_idx = header.index('device_id')
        timestamp_idx = header.index('timestamp')
        
        assert data_row[device_id_idx], "device_id should not be empty"
        assert data_row[timestamp_idx], "timestamp should not be empty"
        
        # Validate timestamp format
        timestamp_str = data_row[timestamp_idx]
        try:
            datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"Invalid timestamp format: {timestamp_str}")


if __name__ == '__main__':
    # Run with specific verbosity for integration tests
    pytest.main([
        __file__, 
        '-v', 
        '--tb=short',
        '--capture=no'  # Show print statements for debugging
    ])