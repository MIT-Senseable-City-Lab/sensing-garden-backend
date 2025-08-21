"""
Tests for CSV flattening utility functions.
"""

import pytest
import json
from decimal import Decimal
from unittest.mock import patch

# Import the CSV utils module
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda', 'src'))

from csv_utils import (
    flatten_dynamodb_item,
    generate_csv_from_dynamodb_items,
    generate_complete_csv,
    create_csv_response,
    _flatten_bounding_box,
    _flatten_location,
    _flatten_classification_data,
    _flatten_metadata,
    _safe_str
)


class TestSafeStr:
    """Test the _safe_str utility function."""
    
    def test_none_values(self):
        assert _safe_str(None) == ""
    
    def test_boolean_values(self):
        assert _safe_str(True) == "true"
        assert _safe_str(False) == "false"
    
    def test_decimal_values(self):
        assert _safe_str(Decimal('123.45')) == "123.45"
        assert _safe_str(Decimal('0')) == "0.0"
    
    def test_numeric_values(self):
        assert _safe_str(123) == "123"
        assert _safe_str(45.67) == "45.67"
    
    def test_string_values(self):
        assert _safe_str("test") == "test"
        assert _safe_str("") == ""
    
    def test_complex_objects(self):
        assert _safe_str([1, 2, 3]) == "[1, 2, 3]"
        assert _safe_str({"key": "value"}) == '{"key": "value"}'


class TestFlattenBoundingBox:
    """Test bounding box flattening."""
    
    def test_valid_bounding_box(self):
        bbox = [10, 20, 30, 40]
        result = _flatten_bounding_box(bbox)
        expected = {
            'bbox_xmin': '10',
            'bbox_ymin': '20',
            'bbox_xmax': '30',
            'bbox_ymax': '40'
        }
        assert result == expected
    
    def test_decimal_bounding_box(self):
        bbox = [Decimal('10.5'), Decimal('20.7'), Decimal('30.2'), Decimal('40.8')]
        result = _flatten_bounding_box(bbox)
        expected = {
            'bbox_xmin': '10.5',
            'bbox_ymin': '20.7',
            'bbox_xmax': '30.2',
            'bbox_ymax': '40.8'
        }
        assert result == expected
    
    def test_empty_bounding_box(self):
        result = _flatten_bounding_box([])
        expected = {
            'bbox_xmin': '',
            'bbox_ymin': '',
            'bbox_xmax': '',
            'bbox_ymax': ''
        }
        assert result == expected
    
    def test_invalid_bounding_box(self):
        result = _flatten_bounding_box([10, 20])  # Wrong length
        expected = {
            'bbox_xmin': '',
            'bbox_ymin': '',
            'bbox_xmax': '',
            'bbox_ymax': ''
        }
        assert result == expected


class TestFlattenLocation:
    """Test location flattening."""
    
    def test_valid_location(self):
        location = {'lat': 40.7128, 'long': -74.0060, 'alt': 10.5}
        result = _flatten_location(location)
        expected = {
            'latitude': '40.7128',
            'longitude': '-74.006',
            'altitude': '10.5'
        }
        assert result == expected
    
    def test_location_with_decimals(self):
        location = {
            'lat': Decimal('40.7128'), 
            'long': Decimal('-74.0060'), 
            'alt': Decimal('10.5')
        }
        result = _flatten_location(location)
        expected = {
            'latitude': '40.7128',
            'longitude': '-74.006',
            'altitude': '10.5'
        }
        assert result == expected
    
    def test_partial_location(self):
        location = {'lat': 40.7128, 'long': -74.0060}  # No altitude
        result = _flatten_location(location)
        expected = {
            'latitude': '40.7128',
            'longitude': '-74.006',
            'altitude': ''
        }
        assert result == expected
    
    def test_empty_location(self):
        result = _flatten_location({})
        expected = {
            'latitude': '',
            'longitude': '',
            'altitude': ''
        }
        assert result == expected
    
    def test_invalid_location(self):
        result = _flatten_location(None)
        expected = {
            'latitude': '',
            'longitude': '',
            'altitude': ''
        }
        assert result == expected


class TestFlattenClassificationData:
    """Test classification data flattening."""
    
    def test_valid_classification_data(self):
        classification_data = {
            'family': [
                {'name': 'Nymphalidae', 'confidence': 0.95},
                {'name': 'Pieridae', 'confidence': 0.05}
            ],
            'genus': [
                {'name': 'Vanessa', 'confidence': 0.87}
            ],
            'species': [
                {'name': 'cardui', 'confidence': 0.82},
                {'name': 'atalanta', 'confidence': 0.18}
            ]
        }
        
        result = _flatten_classification_data(classification_data)
        
        # Check counts
        assert result['classification_family_count'] == '2'
        assert result['classification_genus_count'] == '1'
        assert result['classification_species_count'] == '2'
        
        # Check family candidates
        assert result['classification_family_1_name'] == 'Nymphalidae'
        assert result['classification_family_1_confidence'] == '0.95'
        assert result['classification_family_2_name'] == 'Pieridae'
        assert result['classification_family_2_confidence'] == '0.05'
        
        # Check genus candidates
        assert result['classification_genus_1_name'] == 'Vanessa'
        assert result['classification_genus_1_confidence'] == '0.87'
        
        # Check species candidates
        assert result['classification_species_1_name'] == 'cardui'
        assert result['classification_species_1_confidence'] == '0.82'
    
    def test_empty_classification_data(self):
        result = _flatten_classification_data({})
        assert result == {}
    
    def test_invalid_classification_data(self):
        result = _flatten_classification_data(None)
        assert result == {}


class TestFlattenMetadata:
    """Test metadata flattening."""
    
    def test_simple_metadata(self):
        metadata = {
            'camera_model': 'RaspberryPi Camera v2',
            'resolution': '1920x1080',
            'capture_mode': 'auto'
        }
        result = _flatten_metadata(metadata)
        expected = {
            'metadata_camera_model': 'RaspberryPi Camera v2',
            'metadata_resolution': '1920x1080',
            'metadata_capture_mode': 'auto'
        }
        assert result == expected
    
    def test_nested_metadata(self):
        metadata = {
            'camera': {
                'model': 'RaspberryPi Camera v2',
                'settings': {
                    'iso': 100,
                    'exposure': 'auto'
                }
            },
            'processing': {
                'version': '1.0'
            }
        }
        result = _flatten_metadata(metadata)
        
        assert result['metadata_camera_model'] == 'RaspberryPi Camera v2'
        assert result['metadata_camera_settings_iso'] == '100'
        assert result['metadata_camera_settings_exposure'] == 'auto'
        assert result['metadata_processing_version'] == '1.0'
    
    def test_metadata_with_arrays(self):
        metadata = {
            'tags': ['insect', 'butterfly', 'garden'],
            'processing_steps': ['resize', 'normalize']
        }
        result = _flatten_metadata(metadata)
        
        # Arrays should be JSON encoded
        assert json.loads(result['metadata_tags']) == ['insect', 'butterfly', 'garden']
        assert json.loads(result['metadata_processing_steps']) == ['resize', 'normalize']
    
    def test_empty_metadata(self):
        result = _flatten_metadata({})
        assert result == {}


class TestFlattenDynamodbItem:
    """Test complete item flattening."""
    
    def test_detection_item(self):
        item = {
            'device_id': 'test-device-001',
            'timestamp': '2023-07-15T10:30:00Z',
            'model_id': 'yolov8n-insects-v1.0',
            'image_key': 'detection/test-device-001/2023-07-15-10-30-00.jpg',
            'image_bucket': 'sensing-garden-images',
            'bounding_box': [150, 200, 250, 300]
        }
        
        result = flatten_dynamodb_item(item, 'detection')
        
        assert result['device_id'] == 'test-device-001'
        assert result['timestamp'] == '2023-07-15T10:30:00Z'
        assert result['model_id'] == 'yolov8n-insects-v1.0'
        assert result['image_key'] == 'detection/test-device-001/2023-07-15-10-30-00.jpg'
        assert result['image_bucket'] == 'sensing-garden-images'
        assert result['bbox_xmin'] == '150'
        assert result['bbox_ymin'] == '200'
        assert result['bbox_xmax'] == '250'
        assert result['bbox_ymax'] == '300'
    
    def test_classification_item_with_environment(self):
        item = {
            'device_id': 'test-device-001',
            'timestamp': '2023-07-15T10:30:00Z',
            'model_id': 'classifier-v1.0',
            'image_key': 'classification/test-device-001/2023-07-15-10-30-00.jpg',
            'image_bucket': 'sensing-garden-images',
            'family': 'Nymphalidae',
            'genus': 'Vanessa',
            'species': 'cardui',
            'family_confidence': Decimal('0.95'),
            'genus_confidence': Decimal('0.87'),
            'species_confidence': Decimal('0.82'),
            'location': {
                'lat': Decimal('40.7128'),
                'long': Decimal('-74.0060'),
                'alt': Decimal('10.5')
            },
            'pm1p0': Decimal('12.5'),
            'pm2p5': Decimal('18.3'),
            'ambient_temperature': Decimal('23.4'),
            'ambient_humidity': Decimal('65.2'),
            'metadata': {
                'camera_model': 'RaspberryPi Camera v2'
            }
        }
        
        result = flatten_dynamodb_item(item, 'classification')
        
        # Check standard fields
        assert result['device_id'] == 'test-device-001'
        assert result['family'] == 'Nymphalidae'
        assert result['genus'] == 'Vanessa'
        assert result['species'] == 'cardui'
        assert result['family_confidence'] == '0.95'
        
        # Check location flattening
        assert result['latitude'] == '40.7128'
        assert result['longitude'] == '-74.006'
        assert result['altitude'] == '10.5'
        
        # Check environmental data
        assert result['pm1p0'] == '12.5'
        assert result['pm2p5'] == '18.3'
        assert result['ambient_temperature'] == '23.4'
        assert result['ambient_humidity'] == '65.2'
        
        # Check metadata flattening
        assert result['metadata_camera_model'] == 'RaspberryPi Camera v2'


class TestCSVGeneration:
    """Test CSV generation functions."""
    
    def test_generate_csv_from_items(self):
        items = [
            {
                'device_id': 'device-001',
                'timestamp': '2023-07-15T10:30:00Z',
                'family': 'Nymphalidae',
                'genus': 'Vanessa',
                'species': 'cardui'
            },
            {
                'device_id': 'device-002',
                'timestamp': '2023-07-15T11:00:00Z',
                'family': 'Pieridae',
                'genus': 'Pieris',
                'species': 'rapae'
            }
        ]
        
        header, data_rows = generate_csv_from_dynamodb_items(items, 'classification')
        
        # Check header is present and contains expected columns
        assert header is not None
        assert 'device_id' in header
        assert 'timestamp' in header
        assert 'family' in header
        
        # Check data rows
        assert len(data_rows) == 2
        assert 'device-001' in data_rows[0]
        assert 'device-002' in data_rows[1]
    
    def test_generate_complete_csv(self):
        items = [
            {
                'device_id': 'device-001',
                'family': 'Nymphalidae',
                'bounding_box': [10, 20, 30, 40]
            }
        ]
        
        csv_content = generate_complete_csv(items, 'classification')
        
        # Should contain header and data
        lines = csv_content.split('\n')
        assert len(lines) == 2  # Header + 1 data row
        
        # Header should contain flattened bbox columns
        header = lines[0]
        assert 'bbox_xmin' in header
        assert 'bbox_ymin' in header
        assert 'bbox_xmax' in header
        assert 'bbox_ymax' in header
        
        # Data should contain bbox values
        data_row = lines[1]
        assert '10' in data_row
        assert '20' in data_row
        assert '30' in data_row
        assert '40' in data_row
    
    def test_empty_items_csv(self):
        header, data_rows = generate_csv_from_dynamodb_items([], 'classification')
        assert header is None
        assert data_rows == []
        
        csv_content = generate_complete_csv([], 'classification')
        assert csv_content == ""
    
    def test_create_csv_response(self):
        items = [
            {
                'device_id': 'device-001',
                'family': 'Nymphalidae'
            }
        ]
        
        response = create_csv_response(items, 'classification', 'test.csv')
        
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'text/csv'
        assert 'test.csv' in response['headers']['Content-Disposition']
        assert 'device-001' in response['body']
        assert 'Nymphalidae' in response['body']
    
    def test_csv_response_error_handling(self):
        # Test with invalid data that should cause an error
        with patch('csv_utils.generate_complete_csv', side_effect=Exception('Test error')):
            response = create_csv_response([{}], 'classification')
            
            assert response['statusCode'] == 500
            assert response['headers']['Content-Type'] == 'application/json'
            assert 'Failed to generate CSV' in response['body']


class TestCSVColumnOrdering:
    """Test CSV column ordering and prioritization."""
    
    def test_column_priority_ordering(self):
        items = [
            {
                'zzz_last_field': 'should_be_last',
                'device_id': 'device-001',
                'bbox_xmin': '10',
                'aaa_custom_field': 'should_be_after_priority',
                'timestamp': '2023-07-15T10:30:00Z',
                'family': 'Nymphalidae'
            }
        ]
        
        header, data_rows = generate_csv_from_dynamodb_items(items, 'classification')
        
        # Parse header to check column order
        columns = [col.strip('"') for col in header.split(',')]
        
        # Priority fields should come first
        device_id_index = columns.index('device_id')
        timestamp_index = columns.index('timestamp')
        family_index = columns.index('family')
        bbox_index = columns.index('bbox_xmin')
        
        # Custom fields should be after priority fields, sorted alphabetically
        aaa_index = columns.index('aaa_custom_field')
        zzz_index = columns.index('zzz_last_field')
        
        # Check priority field ordering
        assert device_id_index < timestamp_index
        assert timestamp_index < family_index
        assert family_index < bbox_index
        
        # Check that priority fields come before custom fields
        assert bbox_index < aaa_index
        assert aaa_index < zzz_index  # Alphabetical ordering of custom fields


if __name__ == '__main__':
    pytest.main([__file__])