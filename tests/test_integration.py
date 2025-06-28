"""
Integration tests for complete API workflows.
Tests end-to-end scenarios across multiple endpoints.
"""

import json
import base64
import time
import pytest
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'src'))

from handler import lambda_handler


class TestIntegrationWorkflows:
    """Test complete workflows across multiple endpoints"""
    
    def create_test_image(self):
        """Create a base64 encoded test image"""
        # 1x1 white PNG
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd4l\x00\x00\x00\x00IEND\xaeB`\x82'
        return base64.b64encode(png_data).decode('utf-8')
    
    def test_complete_device_workflow(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test complete device lifecycle: create, use, query, delete"""
        device_id = 'integration-test-device-001'
        
        # 1. Create device
        create_event = api_event('POST', '/devices', body=json.dumps({
            'device_id': device_id,
            'name': 'Integration Test Device',
            'location': 'Test Garden'
        }))
        response = lambda_handler(create_event, lambda_context)
        assert response['statusCode'] == 200
        
        # 2. Upload detection from device
        detection_event = api_event('POST', '/detections', body=json.dumps({
            'device_id': device_id,
            'model_id': 'yolov8-test',
            'image': self.create_test_image(),
            'confidence': 0.89,
            'object_class': 'butterfly',
            'bounding_box': [10, 20, 50, 60]
        }))
        response = lambda_handler(detection_event, lambda_context)
        assert response['statusCode'] == 200
        
        # 3. Upload classification
        classification_event = api_event('POST', '/classifications', body=json.dumps({
            'device_id': device_id,
            'model_id': 'insect-classifier-v1',
            'image': self.create_test_image(),
            'family': 'Lepidoptera',
            'genus': 'Vanessa',
            'species': 'Vanessa cardui',
            'family_confidence': 0.95,
            'genus_confidence': 0.87,
            'species_confidence': 0.73,
            'track_id': 'track-001',
            'family_confidence_array': [0.95, 0.03, 0.01, 0.01]
        }))
        response = lambda_handler(classification_event, lambda_context)
        assert response['statusCode'] == 200
        
        # 4. Query all data for device
        get_detections = api_event('GET', '/detections', query_params={'device_id': device_id})
        det_response = lambda_handler(get_detections, lambda_context)
        assert det_response['statusCode'] == 200
        det_body = json.loads(det_response['body'])
        assert len(det_body['items']) == 1
        assert det_body['items'][0]['object_class'] == 'butterfly'
        
        get_classifications = api_event('GET', '/classifications', query_params={'device_id': device_id})
        class_response = lambda_handler(get_classifications, lambda_context)
        assert class_response['statusCode'] == 200
        class_body = json.loads(class_response['body'])
        assert len(class_body['items']) == 1
        assert class_body['items'][0]['species'] == 'Vanessa cardui'
        assert 'family_confidence_array' in class_body['items'][0]
        
        # 5. Count operations
        count_det = api_event('GET', '/detections/count', query_params={'device_id': device_id})
        count_response = lambda_handler(count_det, lambda_context)
        assert json.loads(count_response['body'])['count'] == 1
        
        # 6. Delete device
        delete_event = api_event('DELETE', '/devices', query_params={'device_id': device_id})
        response = lambda_handler(delete_event, lambda_context)
        assert response['statusCode'] == 200
    
    def test_multi_device_tracking(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test tracking multiple devices with different data"""
        devices = ['garden-device-001', 'garden-device-002', 'garden-device-003']
        
        # Create devices
        for device_id in devices:
            event = api_event('POST', '/devices', body=json.dumps({'device_id': device_id}))
            lambda_handler(event, lambda_context)
        
        # Each device uploads different numbers of detections
        for i, device_id in enumerate(devices):
            for j in range(i + 1):  # Device 1: 1 detection, Device 2: 2 detections, etc.
                event = api_event('POST', '/detections', body=json.dumps({
                    'device_id': device_id,
                    'model_id': 'yolov8-test',
                    'image': self.create_test_image(),
                    'confidence': 0.85 + j * 0.01,
                    'object_class': f'insect_type_{j}'
                }))
                lambda_handler(event, lambda_context)
        
        # Verify counts for each device
        for i, device_id in enumerate(devices):
            event = api_event('GET', '/detections/count', query_params={'device_id': device_id})
            response = lambda_handler(event, lambda_context)
            count = json.loads(response['body'])['count']
            assert count == i + 1
    
    def test_time_series_data(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test handling time series data with proper ordering"""
        device_id = 'time-series-device'
        
        # Create device
        event = api_event('POST', '/devices', body=json.dumps({'device_id': device_id}))
        lambda_handler(event, lambda_context)
        
        # Upload detections at different times
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        timestamps = []
        
        for i in range(5):
            timestamp = base_time.replace(hour=12 + i).isoformat()
            timestamps.append(timestamp)
            
            event = api_event('POST', '/detections', body=json.dumps({
                'device_id': device_id,
                'model_id': 'yolov8-test',
                'timestamp': timestamp,
                'image': self.create_test_image(),
                'confidence': 0.9,
                'object_class': f'insect_hour_{12 + i}'
            }))
            lambda_handler(event, lambda_context)
        
        # Query with time range
        start_time = base_time.replace(hour=13).isoformat()
        end_time = base_time.replace(hour=15).isoformat()
        
        event = api_event('GET', '/detections', query_params={
            'device_id': device_id,
            'start_time': start_time,
            'end_time': end_time
        })
        response = lambda_handler(event, lambda_context)
        body = json.loads(response['body'])
        
        # Should get hours 13 and 14 (not 15, as end_time is exclusive)
        assert len(body['items']) == 2
        assert body['items'][0]['object_class'] == 'insect_hour_13'
        assert body['items'][1]['object_class'] == 'insect_hour_14'
    
    def test_model_versioning(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test handling different model versions"""
        # Upload model information
        models = [
            {'id': 'yolov8-v1', 'type': 'detection', 'version': '1.0'},
            {'id': 'yolov8-v2', 'type': 'detection', 'version': '2.0'},
            {'id': 'classifier-v1', 'type': 'classification', 'version': '1.0'}
        ]
        
        for model in models:
            event = api_event('POST', '/models', body=json.dumps(model))
            response = lambda_handler(event, lambda_context)
            assert response['statusCode'] == 200
        
        # Query models
        event = api_event('GET', '/models')
        response = lambda_handler(event, lambda_context)
        body = json.loads(response['body'])
        
        assert len(body['items']) >= 3
        model_ids = [m['id'] for m in body['items']]
        assert 'yolov8-v1' in model_ids
        assert 'yolov8-v2' in model_ids
        assert 'classifier-v1' in model_ids
    
    def test_video_registration_workflow(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test video registration and retrieval workflow"""
        device_id = 'video-device-001'
        
        # Create device
        event = api_event('POST', '/devices', body=json.dumps({'device_id': device_id}))
        lambda_handler(event, lambda_context)
        
        # Register video metadata
        video_data = {
            'device_id': device_id,
            'video_key': 'videos/2024/01/01/garden_timelapse.mp4',
            'video_bucket': 'test-sensing-garden-videos',
            'duration': 300,  # 5 minutes
            'size': 50000000,  # 50MB
            'timestamp': '2024-01-01T12:00:00Z'
        }
        
        event = api_event('POST', '/videos/register', body=json.dumps(video_data))
        response = lambda_handler(event, lambda_context)
        assert response['statusCode'] == 200
        
        # Query videos
        event = api_event('GET', '/videos', query_params={'device_id': device_id})
        response = lambda_handler(event, lambda_context)
        body = json.loads(response['body'])
        
        assert len(body['items']) == 1
        video = body['items'][0]
        assert video['duration'] == 300
        assert video['size'] == 50000000
        assert 'presigned_url' in video  # Should have presigned URL for access
    
    def test_error_recovery(self, api_event, lambda_context, dynamodb_tables, s3_buckets):
        """Test system behavior with various error conditions"""
        # Try to query non-existent device
        event = api_event('GET', '/detections', query_params={'device_id': 'non-existent-device'})
        response = lambda_handler(event, lambda_context)
        assert response['statusCode'] == 200  # Should return empty results, not error
        body = json.loads(response['body'])
        assert len(body['items']) == 0
        
        # Try to delete non-existent device
        event = api_event('DELETE', '/devices', query_params={'device_id': 'non-existent-device'})
        response = lambda_handler(event, lambda_context)
        assert response['statusCode'] == 200  # Should succeed (idempotent)
        
        # Try invalid confidence value
        event = api_event('POST', '/detections', body=json.dumps({
            'device_id': 'test-device',
            'model_id': 'test-model',
            'image': self.create_test_image(),
            'confidence': 1.5,  # Invalid: > 1.0
            'object_class': 'test'
        }))
        response = lambda_handler(event, lambda_context)
        assert response['statusCode'] == 400  # Should reject invalid data