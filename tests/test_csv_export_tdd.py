"""
Test-Driven Development (TDD) tests for CSV export functionality.

This file contains failing tests that describe expected behavior for CSV export
features that are either not fully implemented or need improvement. These tests
follow the TDD pattern: write failing tests that describe how the system SHOULD work.
"""

import pytest
import json
from decimal import Decimal
from unittest.mock import patch, Mock
from datetime import datetime, timezone

# Import the modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda', 'src'))

import handler
import csv_utils
import dynamodb


class TestUnifiedCSVExportTDD:
    """TDD tests for unified CSV export endpoint."""
    
    def test_export_endpoint_requires_table_parameter(self):
        """Test that /export endpoint fails without table parameter."""
        event = {
            'queryStringParameters': {
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        # Should fail validation
        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'table parameter is required' in response_body['error']
    
    def test_export_endpoint_validates_table_parameter(self):
        """Test that /export endpoint validates table parameter values."""
        event = {
            'queryStringParameters': {
                'table': 'invalid_table',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        # Should fail validation
        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'Invalid table parameter' in response_body['error']
        assert 'detections, classifications, models, videos, environment, devices' in response_body['error']
    
    def test_export_endpoint_requires_time_parameters(self):
        """Test that /export endpoint requires both start_time and end_time."""
        # Test missing both
        event = {
            'queryStringParameters': {
                'table': 'detections'
            }
        }
        
        response = handler.handle_csv_export(event)
        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'Both start_time and end_time parameters are required' in response_body['error']
        
        # Test missing end_time only
        event['queryStringParameters']['start_time'] = '2023-07-01T00:00:00Z'
        response = handler.handle_csv_export(event)
        assert response['statusCode'] == 400
        
        # Test missing start_time only
        event['queryStringParameters'] = {
            'table': 'detections',
            'end_time': '2023-07-31T23:59:59Z'
        }
        response = handler.handle_csv_export(event)
        assert response['statusCode'] == 400
    
    def test_export_endpoint_validates_date_format(self):
        """Test that /export endpoint validates ISO 8601 date format."""
        event = {
            'queryStringParameters': {
                'table': 'detections',
                'start_time': 'invalid-date-format',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'Invalid date format' in response_body['error']
        assert 'ISO 8601 format' in response_body['error']
    
    @patch('handler.dynamodb.query_data')
    def test_export_endpoint_handles_large_datasets_with_pagination(self, mock_query):
        """Test that /export endpoint properly handles large datasets by paginating."""
        # Mock multiple pages of results
        page1_items = [{'device_id': f'device-{i}', 'timestamp': '2023-07-15T10:30:00Z'} for i in range(5000)]
        page2_items = [{'device_id': f'device-{i}', 'timestamp': '2023-07-15T11:30:00Z'} for i in range(5000, 7500)]
        
        # Mock paginated responses
        mock_query.side_effect = [
            {'items': page1_items, 'next_token': 'page2_token'},
            {'items': page2_items, 'next_token': None}  # No more pages
        ]
        
        event = {
            'queryStringParameters': {
                'table': 'detections',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        # Should succeed and include all data
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'text/csv'
        
        csv_content = response['body']
        lines = csv_content.split('\n')
        
        # Should have header + 7500 data rows
        assert len(lines) == 7501  # header + data rows
        
        # Should contain devices from both pages
        csv_content_str = str(csv_content)
        assert 'device-0' in csv_content_str  # From page 1
        assert 'device-7499' in csv_content_str  # From page 2
        
        # Should have called query_data twice with pagination tokens
        assert mock_query.call_count == 2
        
        # First call should have no next_token
        first_call = mock_query.call_args_list[0]
        assert first_call[1]['next_token'] is None
        
        # Second call should have the pagination token
        second_call = mock_query.call_args_list[1]
        assert second_call[1]['next_token'] == 'page2_token'
    
    @patch('handler.dynamodb.query_data')
    def test_export_endpoint_handles_empty_results(self, mock_query):
        """Test that /export endpoint handles empty results gracefully."""
        mock_query.return_value = {'items': []}
        
        event = {
            'queryStringParameters': {
                'table': 'classifications',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        # Should return empty CSV with proper headers
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'text/csv'
        
        # Should include helpful message about no data
        assert 'No data found' in response['body']
        assert 'classifications' in response['body']
        assert '2023-07-01T00:00:00Z' in response['body']
    
    def test_export_filename_sanitization(self):
        """Test that export filenames are properly sanitized to be filesystem-safe."""
        event = {
            'queryStringParameters': {
                'table': 'detections',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z',
                'filename': 'my file with spaces & special chars!.csv'
            }
        }
        
        with patch('handler.dynamodb.query_data') as mock_query:
            mock_query.return_value = {'items': [{'device_id': 'test'}]}
            
            response = handler.handle_csv_export(event)
            
            assert response['statusCode'] == 200
            content_disposition = response['headers']['Content-Disposition']
            
            # Filename should be sanitized (no spaces or special chars)
            assert 'my_file_with_spaces___special_chars_.csv' in content_disposition
    
    @patch('handler.dynamodb.query_data')
    def test_export_endpoint_prevents_infinite_loops(self, mock_query):
        """Test that export endpoint prevents infinite loops with safety limits."""
        # Mock infinite pagination scenario
        mock_query.return_value = {
            'items': [{'device_id': 'test'}],
            'next_token': 'always_has_more'  # This would cause infinite loop
        }
        
        event = {
            'queryStringParameters': {
                'table': 'detections',
                'start_time': '2023-07-01T00:00:00Z', 
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        # Should complete successfully despite infinite pagination
        assert response['statusCode'] == 200
        
        # Should have hit the safety limit (50 iterations)
        assert mock_query.call_count == 50


class TestComplexClassificationDataCSVTDD:
    """TDD tests for complex classification_data array flattening in CSV."""
    
    def test_classification_data_with_multiple_levels_and_candidates(self):
        """Test CSV flattening with complex classification_data containing all taxonomic levels."""
        classification_data = {
            'family': [
                {'name': 'Nymphalidae', 'confidence': Decimal('0.95')},
                {'name': 'Pieridae', 'confidence': Decimal('0.04')},
                {'name': 'Lycaenidae', 'confidence': Decimal('0.01')}
            ],
            'genus': [
                {'name': 'Vanessa', 'confidence': Decimal('0.87')},
                {'name': 'Danaus', 'confidence': Decimal('0.13')}
            ],
            'species': [
                {'name': 'cardui', 'confidence': Decimal('0.82')},
                {'name': 'atalanta', 'confidence': Decimal('0.15')},
                {'name': 'virginensis', 'confidence': Decimal('0.03')}
            ]
        }
        
        item = {
            'device_id': 'test-device',
            'timestamp': '2023-07-15T10:30:00Z',
            'classification_data': classification_data,
            'family': 'Nymphalidae',
            'genus': 'Vanessa', 
            'species': 'cardui'
        }
        
        result = csv_utils.flatten_dynamodb_item(item, 'classification')
        
        # Should have counts for all levels
        assert result['classification_family_count'] == '3'
        assert result['classification_genus_count'] == '2'
        assert result['classification_species_count'] == '3'
        
        # Should have top 3 candidates for family
        assert result['classification_family_1_name'] == 'Nymphalidae'
        assert result['classification_family_1_confidence'] == '0.95'
        assert result['classification_family_2_name'] == 'Pieridae' 
        assert result['classification_family_2_confidence'] == '0.04'
        assert result['classification_family_3_name'] == 'Lycaenidae'
        assert result['classification_family_3_confidence'] == '0.01'
        
        # Should have top 2 candidates for genus (only 2 available)
        assert result['classification_genus_1_name'] == 'Vanessa'
        assert result['classification_genus_1_confidence'] == '0.87'
        assert result['classification_genus_2_name'] == 'Danaus'
        assert result['classification_genus_2_confidence'] == '0.13'
        
        # Should not have classification_genus_3_* fields since only 2 candidates
        assert 'classification_genus_3_name' not in result
        assert 'classification_genus_3_confidence' not in result
    
    def test_csv_export_with_classification_data_column_ordering(self):
        """Test that classification_data columns are properly ordered in CSV output."""
        items = [{
            'device_id': 'device-001',
            'classification_data': {
                'family': [{'name': 'Nymphalidae', 'confidence': Decimal('0.95')}],
                'genus': [{'name': 'Vanessa', 'confidence': Decimal('0.87')}],
                'species': [{'name': 'cardui', 'confidence': Decimal('0.82')}]
            }
        }]
        
        csv_content = csv_utils.generate_complete_csv(items, 'classification')
        lines = csv_content.split('\n')
        header = lines[0]
        
        # Parse header columns
        columns = [col.strip('"') for col in header.split(',')]
        
        # Find positions of classification data columns
        family_count_idx = columns.index('classification_family_count')
        family_1_name_idx = columns.index('classification_family_1_name')
        family_1_conf_idx = columns.index('classification_family_1_confidence')
        genus_count_idx = columns.index('classification_genus_count')
        species_count_idx = columns.index('classification_species_count')
        
        # Classification columns should be grouped logically
        # Family columns should come together
        assert family_1_name_idx == family_count_idx + 1
        assert family_1_conf_idx == family_1_name_idx + 1
        
        # Family should come before genus, genus before species
        assert family_count_idx < genus_count_idx < species_count_idx
    
    @patch('handler.dynamodb.query_data')
    def test_classifications_csv_export_with_complex_data(self, mock_query):
        """Test full CSV export with complex classification data."""
        mock_items = [{
            'device_id': 'device-001',
            'timestamp': '2023-07-15T10:30:00Z',
            'model_id': 'classifier-v2.0',
            'family': 'Nymphalidae',
            'genus': 'Vanessa',
            'species': 'cardui',
            'family_confidence': Decimal('0.95'),
            'genus_confidence': Decimal('0.87'),
            'species_confidence': Decimal('0.82'),
            'classification_data': {
                'family': [
                    {'name': 'Nymphalidae', 'confidence': Decimal('0.95')},
                    {'name': 'Pieridae', 'confidence': Decimal('0.05')}
                ],
                'genus': [
                    {'name': 'Vanessa', 'confidence': Decimal('0.87')},
                    {'name': 'Danaus', 'confidence': Decimal('0.08')},
                    {'name': 'Heliconius', 'confidence': Decimal('0.05')}
                ]
            },
            'bounding_box': [100, 150, 200, 250],
            'location': {
                'lat': Decimal('40.7128'),
                'long': Decimal('-74.0060')
            },
            'pm1p0': Decimal('12.5'),
            'ambient_temperature': Decimal('23.4')
        }]
        
        mock_query.return_value = {'items': mock_items}
        
        event = {
            'queryStringParameters': {
                'device_id': 'device-001'
            }
        }
        
        response = handler.handle_csv_classifications(event)
        
        assert response['statusCode'] == 200
        csv_content = response['body']
        
        # Should contain all flattened classification data
        assert 'classification_family_count,2' in csv_content.replace(' ', '')
        assert 'classification_genus_count,3' in csv_content.replace(' ', '')
        assert 'Nymphalidae' in csv_content
        assert 'Vanessa' in csv_content
        assert 'Danaus' in csv_content
        assert 'Heliconius' in csv_content
        
        # Should also contain other flattened data
        assert 'bbox_xmin' in csv_content
        assert 'latitude' in csv_content
        assert 'pm1p0' in csv_content
        
        lines = csv_content.split('\n')
        header_line = lines[0]
        data_line = lines[1]
        
        # Verify specific values in data row
        assert '100' in data_line  # bbox_xmin
        assert '40.7128' in data_line  # latitude
        assert '12.5' in data_line  # pm1p0


class TestCSVExportPerformanceAndScalabilityTDD:
    """TDD tests for CSV export performance with large datasets."""
    
    @patch('handler.dynamodb.query_data')
    def test_large_dataset_memory_efficiency(self, mock_query):
        """Test that CSV export handles large datasets without memory issues."""
        # Simulate a very large dataset (10,000 items)
        large_dataset = []
        for i in range(10000):
            large_dataset.append({
                'device_id': f'device-{i % 100}',  # 100 different devices
                'timestamp': f'2023-07-15T{i % 24:02d}:30:00Z',
                'family': 'Nymphalidae',
                'genus': 'Vanessa',
                'species': 'cardui',
                'classification_data': {
                    'family': [
                        {'name': 'Nymphalidae', 'confidence': Decimal('0.95')},
                        {'name': 'Pieridae', 'confidence': Decimal('0.05')}
                    ]
                },
                'location': {
                    'lat': Decimal('40.7128'),
                    'long': Decimal('-74.0060')
                },
                'metadata': {
                    'camera_model': 'RaspberryPi Camera v2',
                    'processing': {
                        'version': '1.0',
                        'algorithm': 'yolov8'
                    }
                }
            })
        
        # Mock paginated response (simulate 2 pages of 5000 items each)
        mock_query.side_effect = [
            {'items': large_dataset[:5000], 'next_token': 'token1'},
            {'items': large_dataset[5000:], 'next_token': None}
        ]
        
        event = {
            'queryStringParameters': {
                'table': 'classifications',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        # Should successfully handle large dataset
        assert response['statusCode'] == 200
        
        csv_content = response['body']
        lines = csv_content.split('\n')
        
        # Should have header + 10,000 data rows
        assert len(lines) == 10001
        
        # Should contain flattened data from first and last items
        assert 'device-0' in csv_content
        assert 'device-99' in csv_content
        
        # Should properly flatten complex nested data even with large dataset
        assert 'classification_family_1_name' in lines[0]  # header
        assert 'metadata_camera_model' in lines[0]  # header
        assert 'metadata_processing_version' in lines[0]  # header
    
    def test_csv_generation_streaming_simulation(self):
        """Test CSV generation with streaming-like behavior for memory efficiency."""
        # Create a dataset that would be problematic if loaded entirely into memory
        items = []
        for i in range(1000):
            items.append({
                'device_id': f'device-{i}',
                'timestamp': f'2023-07-15T10:30:{i%60:02d}Z',
                'classification_data': {
                    'family': [{'name': f'Family_{i%10}', 'confidence': Decimal(str(0.9 - (i%10)*0.01))}],
                    'genus': [{'name': f'Genus_{i%20}', 'confidence': Decimal(str(0.8 - (i%20)*0.01))}],
                    'species': [{'name': f'Species_{i}', 'confidence': Decimal(str(0.7 - (i%5)*0.02))}]
                },
                'metadata': {
                    'batch': i // 100,
                    'processing_time': f'{i*0.5:.2f}s',
                    'complex_data': [f'item_{j}' for j in range(i % 10)]  # Variable sized arrays
                }
            })
        
        # Generate CSV - this should work efficiently even with complex data
        csv_content = csv_utils.generate_complete_csv(items, 'classification')
        
        # Verify the content is correct
        lines = csv_content.split('\n')
        assert len(lines) == 1001  # Header + 1000 data rows
        
        # Check that complex data is properly flattened
        header = lines[0]
        assert 'classification_family_1_name' in header
        assert 'classification_genus_1_name' in header
        assert 'classification_species_1_name' in header
        assert 'metadata_batch' in header
        assert 'metadata_processing_time' in header
        assert 'metadata_complex_data' in header  # Arrays should be JSON encoded
        
        # Check some data rows
        first_data_row = lines[1]
        assert 'device-0' in first_data_row
        assert 'Family_0' in first_data_row
        
        last_data_row = lines[1000]
        assert 'device-999' in last_data_row
        assert 'Family_9' in last_data_row


class TestCSVExportErrorHandlingTDD:
    """TDD tests for CSV export error scenarios and edge cases."""
    
    @patch('handler.dynamodb.query_data')
    def test_csv_export_handles_corrupted_data(self, mock_query):
        """Test CSV export gracefully handles corrupted or malformed data."""
        # Mock data with various corruption scenarios
        corrupted_items = [
            # Valid item for comparison
            {
                'device_id': 'device-001',
                'timestamp': '2023-07-15T10:30:00Z',
                'family': 'Nymphalidae'
            },
            # Item with None values
            {
                'device_id': 'device-002',
                'timestamp': None,
                'family': None,
                'classification_data': None
            },
            # Item with malformed classification_data
            {
                'device_id': 'device-003',
                'timestamp': '2023-07-15T11:30:00Z',
                'classification_data': 'not_a_dict'  # Should be dict
            },
            # Item with malformed bounding box
            {
                'device_id': 'device-004',
                'timestamp': '2023-07-15T12:30:00Z',
                'bounding_box': [1, 2]  # Should have 4 elements
            },
            # Item with deeply nested metadata that might cause issues
            {
                'device_id': 'device-005',
                'timestamp': '2023-07-15T13:30:00Z',
                'metadata': {
                    'level1': {
                        'level2': {
                            'level3': {
                                'circular_ref': None,  # Simulate complex nesting
                                'large_array': list(range(1000))
                            }
                        }
                    }
                }
            }
        ]
        
        mock_query.return_value = {'items': corrupted_items}
        
        event = {
            'queryStringParameters': {
                'table': 'classifications',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        # Should not fail despite corrupted data
        response = handler.handle_csv_export(event)
        
        assert response['statusCode'] == 200
        csv_content = response['body']
        lines = csv_content.split('\n')
        
        # Should have header + 5 data rows (all corrupted items should be handled)
        assert len(lines) == 6
        
        # Corrupted data should be handled gracefully
        # None values should become empty strings
        # Malformed data should be converted to safe strings
        assert 'device-002' in csv_content
        assert 'device-003' in csv_content
        assert 'device-004' in csv_content
        assert 'device-005' in csv_content
    
    @patch('handler.dynamodb.query_data', side_effect=Exception('Database connection failed'))
    def test_csv_export_handles_database_errors(self, mock_query):
        """Test CSV export handles database connection errors gracefully."""
        event = {
            'queryStringParameters': {
                'table': 'detections',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'Database connection failed' in response_body['error']
    
    @patch('csv_utils.generate_complete_csv', side_effect=MemoryError('Insufficient memory'))
    @patch('handler.dynamodb.query_data')
    def test_csv_export_handles_memory_errors(self, mock_query, mock_csv):
        """Test CSV export handles memory errors when processing large datasets."""
        mock_query.return_value = {'items': [{'device_id': 'test'}]}
        
        event = {
            'queryStringParameters': {
                'table': 'classifications',
                'start_time': '2023-07-01T00:00:00Z',
                'end_time': '2023-07-31T23:59:59Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'Insufficient memory' in response_body['error']
    
    def test_csv_export_with_unicode_and_special_characters(self):
        """Test CSV export properly handles Unicode and special characters."""
        items = [
            {
                'device_id': 'device-unicode-test',
                'timestamp': '2023-07-15T10:30:00Z',
                'family': 'Семейство бабочек',  # Cyrillic
                'genus': 'Vanessa™',  # Special characters
                'species': 'cardui ♀',  # Unicode symbols
                'metadata': {
                    'location_name': 'São Paulo, Brasil',  # Accented characters
                    'notes': 'Found near café 🦋',  # Emoji
                    'description': 'Species with "quotes" and, commas'  # CSV problematic chars
                }
            },
            {
                'device_id': 'device-special-chars',
                'timestamp': '2023-07-15T11:30:00Z', 
                'family': 'Test\nNewline',  # Newline character
                'genus': 'Test\tTab',  # Tab character
                'species': 'Test\r\nCRLF',  # CRLF
                'metadata': {
                    'csv_evil': '","","\n,\r\n'  # Characters that break CSV parsing
                }
            }
        ]
        
        csv_content = csv_utils.generate_complete_csv(items, 'classification')
        
        # Should not fail with Unicode content
        assert len(csv_content) > 0
        
        lines = csv_content.split('\n')
        # Should have header + 2 data rows
        assert len(lines) == 3
        
        # Unicode content should be preserved
        csv_str = str(csv_content)
        assert 'Семейство бабочек' in csv_str
        assert 'Vanessa™' in csv_str
        assert 'cardui ♀' in csv_str
        assert 'São Paulo, Brasil' in csv_str
        
        # Special characters should be properly escaped/handled
        # CSV should parse correctly despite problematic characters
        import csv
        import io
        
        # Verify CSV can be parsed back
        csv_file = io.StringIO(csv_content)
        reader = csv.reader(csv_file)
        rows = list(reader)
        
        # Should have 3 rows (header + 2 data)
        assert len(rows) == 3
        
        # Data should be preserved correctly
        header = rows[0]
        data_row_1 = rows[1] 
        data_row_2 = rows[2]
        
        # Find the family column index
        family_idx = header.index('family')
        genus_idx = header.index('genus')
        
        # Unicode should be preserved
        assert data_row_1[family_idx] == 'Семейство бабочек'
        assert data_row_1[genus_idx] == 'Vanessa™'
        
        # Special characters should be handled
        assert data_row_2[family_idx] == 'Test\nNewline'  # Newlines preserved
        assert data_row_2[genus_idx] == 'Test\tTab'  # Tabs preserved


class TestCSVExportIntegrationTDD:
    """Integration tests for the full CSV export pipeline."""
    
    @patch('handler.dynamodb.query_data')
    @patch('handler.dynamodb.get_devices')
    def test_all_csv_endpoints_consistency(self, mock_get_devices, mock_query):
        """Test that all CSV endpoints return consistent format and structure."""
        # Mock data for all table types
        detection_items = [{'device_id': 'dev1', 'timestamp': '2023-07-15T10:30:00Z', 'bounding_box': [1,2,3,4]}]
        classification_items = [{'device_id': 'dev1', 'timestamp': '2023-07-15T10:30:00Z', 'family': 'TestFamily'}]
        model_items = [{'id': 'model1', 'name': 'Test Model', 'version': '1.0'}]
        video_items = [{'device_id': 'dev1', 'timestamp': '2023-07-15T10:30:00Z', 'video_key': 'test.mp4'}]
        env_items = [{'device_id': 'dev1', 'timestamp': '2023-07-15T10:30:00Z', 'temperature': Decimal('25.5')}]
        device_items = [{'device_id': 'dev1', 'created': '2023-07-01T12:00:00Z'}]
        
        mock_query.side_effect = lambda table_type, **kwargs: {
            'detection': {'items': detection_items},
            'classification': {'items': classification_items},
            'model': {'items': model_items},
            'video': {'items': video_items},
            'environmental_reading': {'items': env_items}
        }.get(table_type, {'items': []})
        
        mock_get_devices.return_value = {'items': device_items}
        
        # Test all CSV endpoints
        endpoints = [
            ('/detections/csv', handler.handle_csv_detections),
            ('/classifications/csv', handler.handle_csv_classifications),
            ('/models/csv', handler.handle_csv_models),
            ('/videos/csv', handler.handle_csv_videos),
            ('/environment/csv', handler.handle_csv_environment),
            ('/devices/csv', handler.handle_csv_devices)
        ]
        
        event = {'queryStringParameters': {}}
        
        for endpoint_path, handler_func in endpoints:
            response = handler_func(event)
            
            # All should return 200
            assert response['statusCode'] == 200, f"Failed for {endpoint_path}"
            
            # All should have proper CSV headers
            assert response['headers']['Content-Type'] == 'text/csv', f"Wrong content type for {endpoint_path}"
            assert 'Content-Disposition' in response['headers'], f"Missing content disposition for {endpoint_path}"
            assert 'attachment' in response['headers']['Content-Disposition'], f"Not attachment for {endpoint_path}"
            
            # All should have CSV content
            csv_content = response['body']
            assert len(csv_content) > 0, f"Empty content for {endpoint_path}"
            
            lines = csv_content.split('\n')
            assert len(lines) >= 1, f"No header for {endpoint_path}"  # At least header
            
            # Header should contain at least device_id or id column (except models which use 'id')
            header = lines[0].lower()
            if endpoint_path == '/models/csv':
                assert 'id' in header, f"Missing id column for {endpoint_path}"
            else:
                assert 'device_id' in header, f"Missing device_id column for {endpoint_path}"
    
    @patch('handler.dynamodb.query_data')  
    def test_unified_export_endpoint_matches_individual_endpoints(self, mock_query):
        """Test that unified /export endpoint returns same data as individual endpoints."""
        test_items = [
            {
                'device_id': 'test-device',
                'timestamp': '2023-07-15T10:30:00Z',
                'family': 'Nymphalidae',
                'genus': 'Vanessa',
                'species': 'cardui',
                'classification_data': {
                    'family': [{'name': 'Nymphalidae', 'confidence': Decimal('0.95')}]
                },
                'location': {'lat': Decimal('40.7128'), 'long': Decimal('-74.0060')},
                'metadata': {'camera': 'test'}
            }
        ]
        
        mock_query.return_value = {'items': test_items}
        
        # Test individual endpoint
        individual_event = {'queryStringParameters': {'device_id': 'test-device'}}
        individual_response = handler.handle_csv_classifications(individual_event)
        
        # Test unified endpoint
        unified_event = {
            'queryStringParameters': {
                'table': 'classifications',
                'start_time': '2023-07-15T00:00:00Z',
                'end_time': '2023-07-15T23:59:59Z',
                'device_id': 'test-device'
            }
        }
        unified_response = handler.handle_csv_export(unified_event)
        
        # Both should succeed
        assert individual_response['statusCode'] == 200
        assert unified_response['statusCode'] == 200
        
        # CSV content should be identical (modulo filename differences)
        individual_csv = individual_response['body']
        unified_csv = unified_response['body']
        
        # Parse both CSV contents
        individual_lines = individual_csv.split('\n')
        unified_lines = unified_csv.split('\n')
        
        # Should have same number of lines
        assert len(individual_lines) == len(unified_lines)
        
        # Headers should be identical
        assert individual_lines[0] == unified_lines[0]
        
        # Data rows should be identical
        if len(individual_lines) > 1:
            assert individual_lines[1] == unified_lines[1]
    
    def test_csv_export_main_handler_routing(self):
        """Test that main Lambda handler routes CSV requests correctly."""
        # Test all CSV endpoint routes
        csv_routes = [
            '/detections/csv',
            '/classifications/csv', 
            '/models/csv',
            '/videos/csv',
            '/environment/csv',
            '/devices/csv',
            '/export'
        ]
        
        for route in csv_routes:
            event = {
                'requestContext': {
                    'http': {
                        'method': 'GET',
                        'path': route
                    }
                },
                'queryStringParameters': {
                    'table': 'detections',
                    'start_time': '2023-07-01T00:00:00Z',
                    'end_time': '2023-07-31T23:59:59Z'
                } if route == '/export' else {}
            }
            
            with patch('handler.dynamodb.query_data') as mock_query:
                with patch('handler.dynamodb.get_devices') as mock_get_devices:
                    mock_query.return_value = {'items': []}
                    mock_get_devices.return_value = {'items': []}
                    
                    response = handler.handler(event, {})
                    
                    # Should route correctly and not return 404
                    assert response['statusCode'] != 404, f"Route {route} not found"
                    
                    # Should return proper response (200 for empty data, or error for missing params)
                    assert response['statusCode'] in [200, 400, 500], f"Unexpected status for {route}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])