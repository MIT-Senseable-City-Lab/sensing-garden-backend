"""
Tests for Lambda handler functions.
Tests all API endpoints with various scenarios.
"""

import json
import base64
import pytest
from decimal import Decimal
from datetime import datetime, timezone

# Import handler module
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'src'))

from handler import lambda_handler

class TestDeviceEndpoints:
    """Test device-related endpoints"""
    
    def test_get_devices_empty(self, api_event, lambda_context, dynamodb_tables):
        """Test GET /devices with no devices"""
        event = api_event('GET', '/devices')
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'items' in body
        assert len(body['items']) == 0
    
    def test_post_device(self, api_event, lambda_context, dynamodb_tables):
        """Test POST /devices to create a new device"""
        device_data = {
            'device_id': 'test-device-001',
            'name': 'Test Garden Device',
            'location': 'Test Garden'
        }
        
        event = api_event('POST', '/devices', body=json.dumps(device_data))
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Device added'
        assert body['device']['device_id'] == 'test-device-001'
    
    def test_get_devices_after_creation(self, api_event, lambda_context, dynamodb_tables):
        """Test GET /devices after creating a device"""
        # First create a device
        device_data = {'device_id': 'test-device-002'}
        event = api_event('POST', '/devices', body=json.dumps(device_data))
        lambda_handler(event, lambda_context)
        
        # Now get devices
        event = api_event('GET', '/devices')
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['items']) == 1
        assert body['items'][0]['device_id'] == 'test-device-002'
    
    def test_delete_device(self, api_event, lambda_context, dynamodb_tables):
        """Test DELETE /devices"""
        # First create a device
        device_data = {'device_id': 'test-device-003'}
        event = api_event('POST', '/devices', body=json.dumps(device_data))
        lambda_handler(event, lambda_context)
        
        # Delete the device
        event = api_event('DELETE', '/devices', query_params={'device_id': 'test-device-003'})
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Device deleted'
    
    def test_post_device_missing_id(self, api_event, lambda_context, dynamodb_tables):
        """Test POST /devices with missing device_id"""
        device_data = {'name': 'Test Device'}  # Missing device_id
        
        event = api_event('POST', '/devices', body=json.dumps(device_data))
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body


class TestClassificationEndpoints:
    """Test classification-related endpoints"""
    
    def create_test_image(self):
        """Create a base64 encoded test image"""
        # 1x1 white PNG
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd4l\x00\x00\x00\x00IEND\xaeB`\x82'
        return base64.b64encode(png_data).decode('utf-8')
    
    def test_post_classification_basic(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test POST /classifications with basic data"""
        classification_data = {
            'device_id': 'test-device-001',
            'model_id': 'test-model-v1',
            'image': self.create_test_image(),
            'family': 'Lepidoptera',
            'genus': 'Vanessa',
            'species': 'Vanessa cardui',
            'family_confidence': 0.95,
            'genus_confidence': 0.87,
            'species_confidence': 0.73
        }
        
        event = api_event('POST', '/classifications', body=json.dumps(classification_data))
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Classification data stored successfully'
        assert 'data' in body
        assert body['data']['species'] == 'Vanessa cardui'
    
    def test_post_classification_with_arrays(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test POST /classifications with confidence arrays"""
        classification_data = {
            'device_id': 'test-device-001',
            'model_id': 'test-model-v2',
            'image': self.create_test_image(),
            'family': 'Lepidoptera',
            'genus': 'Vanessa',
            'species': 'Vanessa cardui',
            'family_confidence': 0.95,
            'genus_confidence': 0.87,
            'species_confidence': 0.73,
            'family_confidence_array': [0.95, 0.03, 0.01, 0.01],
            'genus_confidence_array': [0.87, 0.08, 0.03, 0.02],
            'species_confidence_array': [0.73, 0.15, 0.07, 0.05]
        }
        
        event = api_event('POST', '/classifications', body=json.dumps(classification_data))
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'data' in body
        assert 'family_confidence_array' in body['data']
        assert len(body['data']['family_confidence_array']) == 4
    
    def test_post_classification_with_metadata(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test POST /classifications with metadata"""
        classification_data = {
            'device_id': 'test-device-001',
            'model_id': 'test-model-v1',
            'image': self.create_test_image(),
            'family': 'Coleoptera',
            'genus': 'Coccinella',
            'species': 'Coccinella septempunctata',
            'family_confidence': 0.92,
            'genus_confidence': 0.88,
            'species_confidence': 0.81,
            'track_id': 'track-123',
            'metadata': {
                'temperature': 22.5,
                'humidity': 65,
                'weather': 'sunny'
            }
        }
        
        event = api_event('POST', '/classifications', body=json.dumps(classification_data))
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['data']['track_id'] == 'track-123'
        assert body['data']['metadata']['temperature'] == 22.5
    
    def test_get_classifications(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test GET /classifications"""
        # First create some classifications
        for i in range(3):
            classification_data = {
                'device_id': 'test-device-001',
                'model_id': 'test-model-v1',
                'image': self.create_test_image(),
                'family': 'Lepidoptera',
                'genus': 'Vanessa',
                'species': f'Species {i}',
                'family_confidence': 0.9,
                'genus_confidence': 0.8,
                'species_confidence': 0.7
            }
            event = api_event('POST', '/classifications', body=json.dumps(classification_data))
            lambda_handler(event, lambda_context)
        
        # Get classifications
        event = api_event('GET', '/classifications', query_params={'device_id': 'test-device-001'})
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['items']) == 3
    
    def test_get_classifications_with_pagination(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test GET /classifications with pagination"""
        # Create 5 classifications
        for i in range(5):
            classification_data = {
                'device_id': 'test-device-002',
                'model_id': 'test-model-v1',
                'image': self.create_test_image(),
                'family': 'Lepidoptera',
                'genus': 'Vanessa',
                'species': f'Species {i}',
                'family_confidence': 0.9,
                'genus_confidence': 0.8,
                'species_confidence': 0.7
            }
            event = api_event('POST', '/classifications', body=json.dumps(classification_data))
            lambda_handler(event, lambda_context)
        
        # Get first page
        event = api_event('GET', '/classifications', query_params={
            'device_id': 'test-device-002',
            'limit': '2'
        })
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['items']) == 2
        assert 'next_token' in body
    
    def test_count_classifications(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test GET /classifications/count"""
        # Create some classifications
        for i in range(3):
            classification_data = {
                'device_id': 'test-device-003',
                'model_id': 'test-model-v1',
                'image': self.create_test_image(),
                'family': 'Lepidoptera',
                'genus': 'Vanessa',
                'species': f'Species {i}',
                'family_confidence': 0.9,
                'genus_confidence': 0.8,
                'species_confidence': 0.7
            }
            event = api_event('POST', '/classifications', body=json.dumps(classification_data))
            lambda_handler(event, lambda_context)
        
        # Count classifications
        event = api_event('GET', '/classifications/count', query_params={'device_id': 'test-device-003'})
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['count'] == 3


class TestErrorHandling:
    """Test error handling scenarios"""
    
    def test_invalid_json_body(self, api_event, lambda_context):
        """Test handling of invalid JSON in request body"""
        event = api_event('POST', '/devices', body='invalid json')
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
    
    def test_unknown_endpoint(self, api_event, lambda_context):
        """Test handling of unknown endpoint"""
        event = api_event('GET', '/unknown')
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Not Found'
    
    def test_missing_required_fields(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test handling of missing required fields"""
        # Classification missing required fields
        classification_data = {
            'device_id': 'test-device-001',
            'model_id': 'test-model-v1',
            # Missing: image, family, genus, species, confidence scores
        }
        
        event = api_event('POST', '/classifications', body=json.dumps(classification_data))
        response = lambda_handler(event, lambda_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body