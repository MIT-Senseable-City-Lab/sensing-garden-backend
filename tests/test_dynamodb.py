"""
Tests for DynamoDB operations.
Tests data validation, storage, and retrieval.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'src'))

import dynamodb


class TestDynamoDBOperations:
    """Test DynamoDB module functions"""
    
    def test_store_and_query_detection(self, dynamodb_tables):
        """Test storing and retrieving detection data"""
        detection_data = {
            'device_id': 'test-device-001',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'model_id': 'yolov8-v1',
            'image_key': 'test/image.jpg',
            'image_bucket': 'test-bucket',
            'confidence': Decimal('0.95'),
            'object_class': 'insect'
        }
        
        # Store detection
        dynamodb.store_detection_data(detection_data)
        
        # Query detections
        result = dynamodb.query_data('detection', device_id='test-device-001')
        
        assert 'items' in result
        assert len(result['items']) == 1
        assert result['items'][0]['device_id'] == 'test-device-001'
        assert float(result['items'][0]['confidence']) == 0.95
    
    def test_store_classification_with_arrays(self, dynamodb_tables):
        """Test storing classification with confidence arrays"""
        classification_data = {
            'device_id': 'test-device-001',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'model_id': 'insect-classifier-v1',
            'image_key': 'test/classification.jpg',
            'image_bucket': 'test-bucket',
            'family': 'Lepidoptera',
            'genus': 'Vanessa',
            'species': 'Vanessa cardui',
            'family_confidence': Decimal('0.95'),
            'genus_confidence': Decimal('0.87'),
            'species_confidence': Decimal('0.73'),
            'family_confidence_array': [Decimal('0.95'), Decimal('0.03'), Decimal('0.01'), Decimal('0.01')],
            'genus_confidence_array': [Decimal('0.87'), Decimal('0.08'), Decimal('0.03'), Decimal('0.02')],
            'species_confidence_array': [Decimal('0.73'), Decimal('0.15'), Decimal('0.07'), Decimal('0.05')]
        }
        
        # Store classification
        dynamodb.store_classification_data(classification_data)
        
        # Query classifications
        result = dynamodb.query_data('classification', device_id='test-device-001')
        
        assert len(result['items']) == 1
        item = result['items'][0]
        assert 'family_confidence_array' in item
        assert len(item['family_confidence_array']) == 4
        assert all(isinstance(x, (int, float)) for x in item['family_confidence_array'])
    
    def test_pagination(self, dynamodb_tables):
        """Test pagination with multiple items"""
        # Create 10 detections
        for i in range(10):
            detection_data = {
                'device_id': 'test-device-002',
                'timestamp': f'2024-01-01T12:00:{i:02d}Z',
                'model_id': 'yolov8-v1',
                'image_key': f'test/image_{i}.jpg',
                'image_bucket': 'test-bucket',
                'confidence': Decimal('0.9'),
                'object_class': 'insect'
            }
            dynamodb.store_detection_data(detection_data)
        
        # Query with limit
        result = dynamodb.query_data('detection', device_id='test-device-002', limit=5)
        
        assert len(result['items']) == 5
        assert 'next_token' in result
        
        # Query next page
        result2 = dynamodb.query_data('detection', 
                                     device_id='test-device-002', 
                                     limit=5, 
                                     next_token=result['next_token'])
        
        assert len(result2['items']) == 5
        # Items should be different
        assert result['items'][0]['timestamp'] != result2['items'][0]['timestamp']
    
    def test_time_range_query(self, dynamodb_tables):
        """Test querying with time range"""
        # Create detections at different times
        timestamps = [
            '2024-01-01T10:00:00Z',
            '2024-01-01T12:00:00Z',
            '2024-01-01T14:00:00Z',
            '2024-01-01T16:00:00Z'
        ]
        
        for ts in timestamps:
            detection_data = {
                'device_id': 'test-device-003',
                'timestamp': ts,
                'model_id': 'yolov8-v1',
                'image_key': f'test/image_{ts}.jpg',
                'image_bucket': 'test-bucket',
                'confidence': Decimal('0.9'),
                'object_class': 'insect'
            }
            dynamodb.store_detection_data(detection_data)
        
        # Query specific time range
        result = dynamodb.query_data('detection',
                                   device_id='test-device-003',
                                   start_time='2024-01-01T11:00:00Z',
                                   end_time='2024-01-01T15:00:00Z')
        
        assert len(result['items']) == 2
        assert result['items'][0]['timestamp'] == '2024-01-01T12:00:00Z'
        assert result['items'][1]['timestamp'] == '2024-01-01T14:00:00Z'
    
    def test_count_operations(self, dynamodb_tables):
        """Test count operations"""
        # Create some videos
        for i in range(7):
            video_data = {
                'device_id': 'test-device-004',
                'timestamp': f'2024-01-01T12:00:{i:02d}Z',
                'video_key': f'test/video_{i}.mp4',
                'video_bucket': 'test-bucket',
                'duration': 60,
                'size': 1000000
            }
            dynamodb.store_video_data(video_data)
        
        # Count videos
        count = dynamodb.count_items('video', device_id='test-device-004')
        
        assert count == 7
    
    def test_validation_errors(self, dynamodb_tables):
        """Test data validation"""
        # Invalid detection data (missing required field)
        invalid_data = {
            'device_id': 'test-device-001',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            # Missing: model_id, image_key, image_bucket, confidence, object_class
        }
        
        with pytest.raises(ValueError) as exc_info:
            dynamodb.store_detection_data(invalid_data)
        
        assert 'Missing required field' in str(exc_info.value)
    
    def test_device_operations(self, dynamodb_tables):
        """Test device CRUD operations"""
        # Add device
        result = dynamodb.add_device('test-device-005')
        assert result['statusCode'] == 200
        
        # Get devices
        devices_result = dynamodb.get_devices()
        assert any(d['device_id'] == 'test-device-005' for d in devices_result['items'])
        
        # Delete device
        delete_result = dynamodb.delete_device('test-device-005')
        assert delete_result['statusCode'] == 200
        
        # Verify deletion
        devices_after = dynamodb.get_devices()
        assert not any(d['device_id'] == 'test-device-005' for d in devices_after['items'])
    
    def test_metadata_handling(self, dynamodb_tables):
        """Test storing and retrieving metadata"""
        classification_data = {
            'device_id': 'test-device-001',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'model_id': 'insect-classifier-v1',
            'image_key': 'test/classification.jpg',
            'image_bucket': 'test-bucket',
            'family': 'Lepidoptera',
            'genus': 'Vanessa',
            'species': 'Vanessa cardui',
            'family_confidence': Decimal('0.95'),
            'genus_confidence': Decimal('0.87'),
            'species_confidence': Decimal('0.73'),
            'metadata': {
                'temperature': 22.5,
                'humidity': 65,
                'weather': 'sunny',
                'nested': {
                    'value': 123
                }
            }
        }
        
        # Store classification with metadata
        dynamodb.store_classification_data(classification_data)
        
        # Query and verify metadata
        result = dynamodb.query_data('classification', device_id='test-device-001')
        
        assert len(result['items']) == 1
        metadata = result['items'][0]['metadata']
        assert metadata['temperature'] == 22.5
        assert metadata['nested']['value'] == 123