"""
Tests for CSV export handler integration.
"""

import pytest
import json
from decimal import Decimal
from unittest.mock import patch, Mock

# Import the handler module
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda', 'src'))

import handler


class TestCSVHandlers:
    """Test CSV export endpoint handlers."""
    
    def test_handle_csv_detections(self):
        """Test CSV export for detections."""
        # Mock event with query parameters
        event = {
            'queryStringParameters': {
                'device_id': 'test-device-001',
                'limit': '100',
                'filename': 'test_detections.csv'
            }
        }
        
        # Mock the query_data function
        mock_items = [
            {
                'device_id': 'test-device-001',
                'timestamp': '2023-07-15T10:30:00Z',
                'model_id': 'yolov8n-v1.0',
                'image_key': 'detection/test.jpg',
                'image_bucket': 'test-bucket',
                'bounding_box': [10, 20, 30, 40]
            },
            {
                'device_id': 'test-device-001',
                'timestamp': '2023-07-15T11:00:00Z',
                'model_id': 'yolov8n-v1.0',
                'image_key': 'detection/test2.jpg',
                'image_bucket': 'test-bucket',
                'bounding_box': [15, 25, 35, 45]
            }
        ]
        
        with patch('handler.dynamodb.query_data') as mock_query:
            mock_query.return_value = {'items': mock_items}
            
            response = handler.handle_csv_detections(event)
            
            # Check response structure
            assert response['statusCode'] == 200
            assert response['headers']['Content-Type'] == 'text/csv'
            assert 'test_detections.csv' in response['headers']['Content-Disposition']
            
            # Check CSV content
            csv_content = response['body']
            lines = csv_content.split('\n')
            
            # Should have header + 2 data rows
            assert len(lines) == 3
            
            # Header should contain expected columns
            header = lines[0]
            assert 'device_id' in header
            assert 'timestamp' in header
            assert 'bbox_xmin' in header
            assert 'bbox_ymin' in header
            
            # Data rows should contain the test data
            assert 'test-device-001' in lines[1]
            assert '2023-07-15T10:30:00Z' in lines[1]
            assert '10' in lines[1]  # bbox_xmin
            
            # Verify query_data was called with correct parameters
            mock_query.assert_called_once_with(
                'detection',
                device_id='test-device-001',
                model_id=None,
                start_time=None,
                end_time=None,
                limit=100,
                next_token=None,
                sort_by=None,
                sort_desc=False
            )
    
    def test_handle_csv_classifications_with_complex_data(self):
        """Test CSV export for classifications with complex nested data."""
        event = {
            'queryStringParameters': {
                'device_id': 'test-device-002'
            }
        }
        
        # Mock complex classification data
        mock_items = [
            {
                'device_id': 'test-device-002',
                'timestamp': '2023-07-15T10:30:00Z',
                'model_id': 'classifier-v1.0',
                'image_key': 'classification/test.jpg',
                'image_bucket': 'test-bucket',
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
                'classification_data': {
                    'family': [
                        {'name': 'Nymphalidae', 'confidence': Decimal('0.95')},
                        {'name': 'Pieridae', 'confidence': Decimal('0.05')}
                    ]
                },
                'pm1p0': Decimal('12.5'),
                'ambient_temperature': Decimal('23.4'),
                'metadata': {
                    'camera_model': 'RaspberryPi Camera v2',
                    'settings': {
                        'iso': 100
                    }
                }
            }
        ]
        
        with patch('handler.dynamodb.query_data') as mock_query:
            mock_query.return_value = {'items': mock_items}
            
            response = handler.handle_csv_classifications(event)
            
            # Check response
            assert response['statusCode'] == 200
            assert response['headers']['Content-Type'] == 'text/csv'
            
            # Check CSV content contains flattened data
            csv_content = response['body']
            lines = csv_content.split('\n')
            header = lines[0]
            data_row = lines[1]
            
            # Check location flattening
            assert 'latitude' in header
            assert 'longitude' in header
            assert 'altitude' in header
            assert '40.7128' in data_row
            assert '-74.006' in data_row
            
            # Check classification_data flattening
            assert 'classification_family_count' in header
            assert 'classification_family_1_name' in header
            assert 'classification_family_1_confidence' in header
            assert 'Nymphalidae' in data_row
            assert '0.95' in data_row
            
            # Check environmental data
            assert 'pm1p0' in header
            assert 'ambient_temperature' in header
            assert '12.5' in data_row
            assert '23.4' in data_row
            
            # Check metadata flattening
            assert 'metadata_camera_model' in header
            assert 'metadata_settings_iso' in header
            assert 'RaspberryPi Camera v2' in data_row
            assert '100' in data_row
    
    def test_handle_csv_environment(self):
        """Test CSV export for environmental readings."""
        event = {
            'queryStringParameters': {
                'start_time': '2023-07-15T00:00:00Z',
                'end_time': '2023-07-15T23:59:59Z'
            }
        }
        
        mock_items = [
            {
                'device_id': 'env-device-001',
                'timestamp': '2023-07-15T10:00:00Z',
                'temperature': Decimal('25.5'),
                'humidity': Decimal('65.2'),
                'pm1p0': Decimal('12.3'),
                'pm2p5': Decimal('18.7'),
                'voc_index': Decimal('150'),
                'location': {
                    'lat': Decimal('40.7128'),
                    'long': Decimal('-74.0060')
                }
            }
        ]
        
        with patch('handler.dynamodb.query_data') as mock_query:
            mock_query.return_value = {'items': mock_items}
            
            response = handler.handle_csv_environment(event)
            
            assert response['statusCode'] == 200
            csv_content = response['body']
            
            # Check environmental data is properly flattened
            assert 'temperature' in csv_content
            assert 'humidity' in csv_content
            assert 'pm1p0' in csv_content
            assert 'voc_index' in csv_content
            assert '25.5' in csv_content
            assert '65.2' in csv_content
            
            # Verify query was called correctly (no model_id for environmental readings)
            mock_query.assert_called_once_with(
                'environmental_reading',
                device_id=None,
                model_id=None,
                start_time='2023-07-15T00:00:00Z',
                end_time='2023-07-15T23:59:59Z',
                limit=5000,
                next_token=None,
                sort_by=None,
                sort_desc=False
            )
    
    def test_handle_csv_devices(self):
        """Test CSV export for devices."""
        event = {
            'queryStringParameters': {
                'limit': '50'
            }
        }
        
        mock_items = [
            {
                'device_id': 'device-001',
                'created': '2023-07-01T12:00:00Z'
            },
            {
                'device_id': 'device-002', 
                'created': '2023-07-02T12:00:00Z'
            }
        ]
        
        with patch('handler.dynamodb.get_devices') as mock_get_devices:
            mock_get_devices.return_value = {'items': mock_items}
            
            response = handler.handle_csv_devices(event)
            
            assert response['statusCode'] == 200
            csv_content = response['body']
            
            # Check device data
            assert 'device_id' in csv_content
            assert 'created' in csv_content
            assert 'device-001' in csv_content
            assert 'device-002' in csv_content
            
            # Verify get_devices was called correctly
            mock_get_devices.assert_called_once_with(
                None,  # device_id
                None,  # created
                50,    # limit
                None,  # next_token
                None,  # sort_by
                False  # sort_desc
            )
    
    def test_csv_handler_error_handling(self):
        """Test error handling in CSV handlers."""
        event = {
            'queryStringParameters': {}
        }
        
        # Mock query_data to raise an exception
        with patch('handler.dynamodb.query_data', side_effect=Exception('Database error')):
            response = handler.handle_csv_detections(event)
            
            assert response['statusCode'] == 500
            assert 'Database error' in response['body']
    
    def test_csv_handler_empty_results(self):
        """Test CSV handlers with empty results."""
        event = {
            'queryStringParameters': {
                'device_id': 'non-existent-device'
            }
        }
        
        with patch('handler.dynamodb.query_data') as mock_query:
            mock_query.return_value = {'items': []}
            
            response = handler.handle_csv_classifications(event)
            
            assert response['statusCode'] == 200
            assert response['headers']['Content-Type'] == 'text/csv'
            # Empty results should still return valid CSV response (just no data rows)
            assert len(response['body']) == 0
    
    def test_csv_filename_generation(self):
        """Test automatic filename generation when not provided."""
        event = {
            'queryStringParameters': {
                'device_id': 'test-device'
            }
        }
        
        mock_items = [
            {
                'device_id': 'test-device',
                'timestamp': '2023-07-15T10:30:00Z'
            }
        ]
        
        with patch('handler.dynamodb.query_data') as mock_query:
            mock_query.return_value = {'items': mock_items}
            
            response = handler.handle_csv_detections(event)
            
            assert response['statusCode'] == 200
            content_disposition = response['headers']['Content-Disposition']
            
            # Should contain generated filename with timestamp and table type
            assert 'sensing_garden_detections_' in content_disposition
            assert '.csv' in content_disposition
    
    def test_main_handler_csv_routing(self):
        """Test that main handler correctly routes CSV requests."""
        # Test detection CSV endpoint
        event = {
            'requestContext': {
                'http': {
                    'method': 'GET',
                    'path': '/detections/csv'
                }
            },
            'queryStringParameters': {}
        }
        
        with patch('handler.handle_csv_detections') as mock_handler:
            mock_handler.return_value = {'statusCode': 200, 'body': 'csv_content'}
            
            response = handler.handler(event, {})
            
            mock_handler.assert_called_once_with(event)
            assert response['statusCode'] == 200
        
        # Test classification CSV endpoint
        event['requestContext']['http']['path'] = '/classifications/csv'
        
        with patch('handler.handle_csv_classifications') as mock_handler:
            mock_handler.return_value = {'statusCode': 200, 'body': 'csv_content'}
            
            response = handler.handler(event, {})
            
            mock_handler.assert_called_once_with(event)
            assert response['statusCode'] == 200


if __name__ == '__main__':
    pytest.main([__file__])