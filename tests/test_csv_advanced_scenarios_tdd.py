"""
Advanced TDD tests for CSV export functionality focusing on edge cases,
performance scenarios, and missing features that should be implemented.
"""

import pytest
import json
from decimal import Decimal
from unittest.mock import patch, Mock, call
from datetime import datetime, timezone
import io

# Import the modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lambda', 'src'))

import handler
import csv_utils
import dynamodb


class TestCSVExportContentTypesAndEncodingTDD:
    """TDD tests for CSV export content types, encoding, and browser compatibility."""
    
    def test_csv_response_headers_for_browser_compatibility(self):
        """Test that CSV responses include proper headers for browser downloads."""
        items = [{'device_id': 'test', 'family': 'TestFamily'}]
        
        response = csv_utils.create_csv_response(items, 'classification', 'test_export.csv')
        
        headers = response['headers']
        
        # Must have proper Content-Type for CSV
        assert headers['Content-Type'] == 'text/csv'
        
        # Must have Content-Disposition for download
        assert 'attachment' in headers['Content-Disposition']
        assert 'filename="test_export.csv"' in headers['Content-Disposition']
        
        # Should have CORS headers for browser compatibility
        assert headers['Access-Control-Allow-Origin'] == '*'
        
        # Should NOT have caching headers (data should be fresh)
        assert 'Cache-Control' not in headers
        assert 'Expires' not in headers
    
    def test_csv_content_encoding_utf8(self):
        """Test that CSV content is properly UTF-8 encoded."""
        items = [
            {
                'device_id': 'test-utf8',
                'family': 'Família com acentos',  # Portuguese with accents
                'genus': 'Gênero',
                'species': 'espécie',
                'metadata': {
                    'location': '北京',  # Chinese characters
                    'notes': 'Emoji test 🦋🌸',
                    'greek': 'αβγδε'  # Greek characters
                }
            }
        ]
        
        response = csv_utils.create_csv_response(items, 'classification')
        csv_content = response['body']
        
        # Should be valid UTF-8
        assert isinstance(csv_content, str)
        
        # UTF-8 content should be preserved
        assert 'Família com acentos' in csv_content
        assert '北京' in csv_content
        assert '🦋🌸' in csv_content
        assert 'αβγδε' in csv_content
        
        # Should be parseable as CSV despite Unicode
        import csv
        import io
        
        csv_file = io.StringIO(csv_content)
        reader = csv.reader(csv_file)
        rows = list(reader)
        
        assert len(rows) >= 2  # Header + at least 1 data row
        
        # Unicode should be preserved in parsed data
        csv_text = '\n'.join([','.join(row) for row in rows])
        assert 'Família com acentos' in csv_text
    
    @patch('handler.dynamodb.query_data')
    def test_large_csv_response_size_handling(self, mock_query):
        """Test handling of very large CSV responses that might hit Lambda limits."""
        # Create a dataset that would generate a very large CSV
        large_dataset = []
        for i in range(10000):  # 10k items with rich data
            large_dataset.append({
                'device_id': f'device-{i:06d}',
                'timestamp': f'2023-07-{(i%30)+1:02d}T{(i%24):02d}:{(i%60):02d}:00Z',
                'family': f'Family_name_that_is_quite_long_{i%100}',
                'genus': f'Genus_name_also_long_{i%50}',
                'species': f'species_name_extended_{i}',
                'classification_data': {
                    'family': [
                        {'name': f'LongFamilyName{j}', 'confidence': Decimal(f'0.{90-j:02d}')} 
                        for j in range(5)  # 5 candidates each
                    ],
                    'genus': [
                        {'name': f'LongGenusName{j}', 'confidence': Decimal(f'0.{80-j:02d}')} 
                        for j in range(3)
                    ],
                    'species': [
                        {'name': f'LongSpeciesName{j}', 'confidence': Decimal(f'0.{70-j:02d}')} 
                        for j in range(3)
                    ]
                },
                'metadata': {
                    'processing': {
                        'algorithm': 'YOLOv8_with_very_long_configuration_name',
                        'parameters': {
                            'confidence_threshold': Decimal('0.5'),
                            'nms_threshold': Decimal('0.4'),
                            'detailed_info': f'Very long description of processing parameters for item {i}'
                        }
                    },
                    'camera_settings': {
                        'iso': 100 + (i % 400),
                        'exposure_time': f'{(i%1000)/1000:.3f}s',
                        'aperture': f'f/{2.8 + (i%50)/10:.1f}'
                    }
                },
                'location': {
                    'lat': Decimal(f'{40.7128 + (i%1000)/10000:.6f}'),
                    'long': Decimal(f'{-74.0060 + (i%1000)/10000:.6f}'),
                    'alt': Decimal(f'{10.5 + (i%100):.1f}')
                }
            })
        
        # Mock paginated response to simulate realistic API behavior
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
        
        # Should succeed despite large size
        assert response['statusCode'] == 200
        
        csv_content = response['body']
        
        # CSV should be substantial in size but manageable
        assert len(csv_content) > 1000000  # At least 1MB
        
        # Should be well-formed CSV
        lines = csv_content.split('\n')
        assert len(lines) == 10001  # Header + 10k rows
        
        # Should contain all expected flattened columns
        header = lines[0]
        assert 'classification_family_1_name' in header
        assert 'classification_family_2_name' in header
        assert 'metadata_processing_algorithm' in header
        assert 'metadata_camera_settings_iso' in header
        
        # Data should be properly formatted
        first_data_row = lines[1]
        last_data_row = lines[10000]
        
        assert 'device-000000' in first_data_row
        assert 'device-009999' in last_data_row


class TestCSVExportFilteringAndQueryingTDD:
    """TDD tests for advanced filtering and querying capabilities in CSV export."""
    
    @patch('handler.dynamodb.query_data')
    def test_csv_export_with_complex_query_parameters(self, mock_query):
        """Test CSV export with multiple filtering parameters combined."""
        mock_items = [
            {
                'device_id': 'device-001',
                'timestamp': '2023-07-15T10:30:00Z',
                'model_id': 'model-v1.0',
                'family': 'Nymphalidae'
            }
        ]
        mock_query.return_value = {'items': mock_items}
        
        event = {
            'queryStringParameters': {
                'table': 'classifications',
                'device_id': 'device-001',
                'model_id': 'model-v1.0',
                'start_time': '2023-07-15T00:00:00Z',
                'end_time': '2023-07-15T23:59:59Z',
                'sort_by': 'timestamp',
                'sort_desc': 'true',
                'limit': '1000'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        assert response['statusCode'] == 200
        
        # Verify that all query parameters were passed to the data query
        mock_query.assert_called_once_with(
            'classification',
            device_id='device-001',
            model_id='model-v1.0',
            start_time='2023-07-15T00:00:00Z',
            end_time='2023-07-15T23:59:59Z',
            limit=5000,  # CSV export uses higher default limit
            next_token=None,
            sort_by='timestamp',
            sort_desc=True
        )
    
    @patch('handler.dynamodb.query_data')
    def test_csv_export_respects_query_filtering(self, mock_query):
        """Test that CSV export only includes items matching the query filters."""
        # Mock filtered results (simulating DynamoDB query filtering)
        filtered_items = [
            {
                'device_id': 'target-device',
                'timestamp': '2023-07-15T10:30:00Z',
                'family': 'Nymphalidae'
            },
            {
                'device_id': 'target-device',
                'timestamp': '2023-07-15T11:30:00Z', 
                'family': 'Pieridae'
            }
        ]
        
        mock_query.return_value = {'items': filtered_items}
        
        event = {
            'queryStringParameters': {
                'table': 'classifications',
                'device_id': 'target-device',  # Filter by specific device
                'start_time': '2023-07-15T10:00:00Z',
                'end_time': '2023-07-15T12:00:00Z'
            }
        }
        
        response = handler.handle_csv_export(event)
        
        assert response['statusCode'] == 200
        csv_content = response['body']
        
        # CSV should only contain the filtered results
        lines = csv_content.split('\n')
        assert len(lines) == 3  # Header + 2 filtered rows
        
        # Both data rows should be for the target device only
        assert 'target-device' in lines[1]
        assert 'target-device' in lines[2]
        assert 'Nymphalidae' in lines[1]
        assert 'Pieridae' in lines[2]
    
    def test_csv_export_date_range_validation_edge_cases(self):
        """Test CSV export date validation handles edge cases correctly."""
        base_event = {
            'queryStringParameters': {
                'table': 'detections'
            }
        }
        
        # Test various invalid date formats
        invalid_dates = [
            ('2023-13-01T00:00:00Z', '2023-12-31T23:59:59Z'),  # Invalid month
            ('2023-07-32T00:00:00Z', '2023-07-31T23:59:59Z'),  # Invalid day
            ('2023-07-15T25:00:00Z', '2023-07-15T23:59:59Z'),  # Invalid hour
            ('2023-07-15T10:70:00Z', '2023-07-15T11:00:00Z'),  # Invalid minute
            ('2023-07-15', '2023-07-16'),  # Missing time component
            ('invalid', 'also-invalid'),  # Completely invalid
            ('2023/07/15 10:30:00', '2023/07/15 11:30:00')  # Wrong separator
        ]
        
        for start_time, end_time in invalid_dates:
            event = base_event.copy()
            event['queryStringParameters'] = {
                'table': 'detections',
                'start_time': start_time,
                'end_time': end_time
            }
            
            response = handler.handle_csv_export(event)
            
            assert response['statusCode'] == 400, f"Should reject invalid dates: {start_time}, {end_time}"
            response_body = json.loads(response['body'])
            assert 'Invalid date format' in response_body['error']
    
    def test_csv_export_handles_timezone_aware_dates(self):
        """Test that CSV export properly handles timezone-aware date filtering."""
        # Test different timezone formats that should be valid
        valid_timezone_dates = [
            ('2023-07-15T10:30:00Z', '2023-07-15T11:30:00Z'),  # UTC (Z)
            ('2023-07-15T10:30:00+00:00', '2023-07-15T11:30:00+00:00'),  # UTC explicit
            ('2023-07-15T10:30:00-05:00', '2023-07-15T11:30:00-05:00'),  # Eastern
            ('2023-07-15T10:30:00.123Z', '2023-07-15T11:30:00.456Z')  # With milliseconds
        ]
        
        for start_time, end_time in valid_timezone_dates:
            event = {
                'queryStringParameters': {
                    'table': 'detections',
                    'start_time': start_time,
                    'end_time': end_time
                }
            }
            
            with patch('handler.dynamodb.query_data') as mock_query:
                mock_query.return_value = {'items': []}
                
                response = handler.handle_csv_export(event)
                
                # Should accept timezone-aware dates
                assert response['statusCode'] == 200, f"Should accept valid timezone dates: {start_time}, {end_time}"


class TestCSVExportBusinessLogicTDD:
    """TDD tests for business logic and domain-specific CSV export functionality."""
    
    def test_csv_export_classification_taxonomic_hierarchy_validation(self):
        """Test CSV export validates taxonomic hierarchy consistency in classification data."""
        items_with_hierarchy_issues = [
            # Valid hierarchy
            {
                'device_id': 'device-001',
                'family': 'Nymphalidae',
                'genus': 'Vanessa',
                'species': 'cardui',
                'classification_data': {
                    'family': [{'name': 'Nymphalidae', 'confidence': Decimal('0.95')}],
                    'genus': [{'name': 'Vanessa', 'confidence': Decimal('0.87')}],
                    'species': [{'name': 'cardui', 'confidence': Decimal('0.82')}]
                }
            },
            # Inconsistent hierarchy (genus doesn't match family)
            {
                'device_id': 'device-002',
                'family': 'Nymphalidae',
                'genus': 'Pieris',  # Should be from Pieridae family
                'species': 'rapae',
                'classification_data': {
                    'family': [{'name': 'Pieridae', 'confidence': Decimal('0.85')}],  # Conflicts with family field
                    'genus': [{'name': 'Pieris', 'confidence': Decimal('0.90')}],
                    'species': [{'name': 'rapae', 'confidence': Decimal('0.75')}]
                }
            },
            # Missing classification data
            {
                'device_id': 'device-003',
                'family': 'Nymphalidae',
                'genus': 'Vanessa',
                'species': 'atalanta'
                # No classification_data field
            }
        ]
        
        csv_content = csv_utils.generate_complete_csv(items_with_hierarchy_issues, 'classification')
        
        # CSV should be generated successfully despite inconsistencies
        lines = csv_content.split('\n')
        assert len(lines) == 4  # Header + 3 data rows
        
        # Should contain both the direct taxonomic fields and flattened classification_data
        header = lines[0]
        assert 'family' in header  # Direct field
        assert 'genus' in header  # Direct field
        assert 'species' in header  # Direct field
        assert 'classification_family_1_name' in header  # From classification_data
        assert 'classification_genus_1_name' in header
        assert 'classification_species_1_name' in header
        
        # Data rows should preserve both representations
        data_row_2 = lines[2]  # The inconsistent one
        assert 'Nymphalidae' in data_row_2  # Direct family field
        assert 'Pieridae' in data_row_2  # From classification_data
        assert 'Pieris' in data_row_2  # Both direct and from classification_data
    
    def test_csv_export_environmental_sensor_data_completeness(self):
        """Test CSV export includes all environmental sensor fields with proper units/context."""
        environmental_item = {
            'device_id': 'env-sensor-001',
            'timestamp': '2023-07-15T10:30:00Z',
            # Particulate Matter sensors
            'pm1p0': Decimal('12.5'),    # μg/m³
            'pm2p5': Decimal('18.3'),    # μg/m³
            'pm4p0': Decimal('22.1'),    # μg/m³
            'pm10p0': Decimal('28.7'),   # μg/m³
            # Climate sensors
            'temperature': Decimal('25.5'),         # °C
            'humidity': Decimal('65.2'),            # %
            'ambient_temperature': Decimal('24.8'), # °C
            'ambient_humidity': Decimal('67.1'),    # %
            'pressure': Decimal('1013.25'),         # hPa
            # Light and UV
            'light_level': Decimal('45000'),        # lux
            'uv_index': Decimal('6.2'),
            # Soil conditions
            'soil_moisture': Decimal('35.8'),       # %
            # Wind conditions  
            'wind_speed': Decimal('3.2'),           # m/s
            'wind_direction': Decimal('145.5'),     # degrees
            # Air quality
            'voc_index': Decimal('150'),            # Index 1-500
            'nox_index': Decimal('75'),             # Index 1-500
            # Location for context
            'location': {
                'lat': Decimal('40.7128'),
                'long': Decimal('-74.0060'),
                'alt': Decimal('10.5')
            }
        }
        
        csv_content = csv_utils.generate_complete_csv([environmental_item], 'environmental_reading')
        lines = csv_content.split('\n')
        header = lines[0].lower()
        data_row = lines[1]
        
        # Should include all environmental sensor fields
        environmental_fields = [
            'pm1p0', 'pm2p5', 'pm4p0', 'pm10p0',
            'temperature', 'humidity', 'ambient_temperature', 'ambient_humidity',
            'pressure', 'light_level', 'uv_index', 'soil_moisture',
            'wind_speed', 'wind_direction', 'voc_index', 'nox_index'
        ]
        
        for field in environmental_fields:
            assert field in header, f"Missing environmental field: {field}"
        
        # Should include location fields
        assert 'latitude' in header
        assert 'longitude' in header
        assert 'altitude' in header
        
        # Data values should be preserved
        assert '12.5' in data_row  # pm1p0
        assert '25.5' in data_row  # temperature
        assert '150' in data_row   # voc_index
        assert '40.7128' in data_row  # latitude
    
    def test_csv_export_detection_bounding_box_coordinate_system(self):
        """Test CSV export handles bounding box coordinates with proper coordinate system context."""
        detection_items = [
            {
                'device_id': 'camera-001',
                'timestamp': '2023-07-15T10:30:00Z',
                'model_id': 'yolov8n-insects-v1.0',
                'bounding_box': [150, 200, 250, 300],  # [xmin, ymin, xmax, ymax]
                'metadata': {
                    'image_dimensions': {
                        'width': 1920,
                        'height': 1080
                    },
                    'coordinate_system': 'pixel_absolute',
                    'detection_confidence': Decimal('0.87')
                }
            },
            {
                'device_id': 'camera-002', 
                'timestamp': '2023-07-15T11:30:00Z',
                'model_id': 'yolov8s-insects-v2.0',
                'bounding_box': [Decimal('0.125'), Decimal('0.185'), Decimal('0.208'), Decimal('0.278')],  # Normalized coordinates
                'metadata': {
                    'coordinate_system': 'normalized',
                    'detection_confidence': Decimal('0.92')
                }
            }
        ]
        
        csv_content = csv_utils.generate_complete_csv(detection_items, 'detection')
        lines = csv_content.split('\n')
        header = lines[0]
        
        # Should have separate columns for each bounding box coordinate
        assert 'bbox_xmin' in header
        assert 'bbox_ymin' in header
        assert 'bbox_xmax' in header
        assert 'bbox_ymax' in header
        
        # Should preserve metadata about coordinate systems
        assert 'metadata_coordinate_system' in header
        assert 'metadata_detection_confidence' in header
        
        # Data should preserve different coordinate formats
        data_row_1 = lines[1]  # Pixel coordinates
        data_row_2 = lines[2]  # Normalized coordinates
        
        assert '150' in data_row_1  # Pixel coordinate
        assert '0.125' in data_row_2  # Normalized coordinate
        assert 'pixel_absolute' in data_row_1
        assert 'normalized' in data_row_2
    
    def test_csv_export_device_tracking_and_temporal_analysis(self):
        """Test CSV export supports device tracking and temporal analysis use cases."""
        # Items spanning multiple devices and time periods
        tracking_items = [
            {
                'device_id': 'garden-east-001',
                'timestamp': '2023-07-15T06:30:00Z',  # Morning
                'family': 'Nymphalidae',
                'genus': 'Vanessa',
                'species': 'cardui',
                'track_id': 'butterfly_track_001',
                'location': {'lat': Decimal('40.7128'), 'long': Decimal('-74.0060')},
                'metadata': {
                    'tracking': {
                        'sequence_number': 1,
                        'track_confidence': Decimal('0.95'),
                        'movement_speed': Decimal('2.3')  # m/s
                    },
                    'environmental_context': {
                        'weather': 'sunny',
                        'temperature_c': Decimal('22.5')
                    }
                }
            },
            {
                'device_id': 'garden-east-001',
                'timestamp': '2023-07-15T06:35:00Z',  # 5 minutes later
                'family': 'Nymphalidae',
                'genus': 'Vanessa', 
                'species': 'cardui',
                'track_id': 'butterfly_track_001',  # Same track
                'location': {'lat': Decimal('40.7129'), 'long': Decimal('-74.0061')},  # Slightly moved
                'metadata': {
                    'tracking': {
                        'sequence_number': 2,
                        'track_confidence': Decimal('0.89'),
                        'movement_speed': Decimal('1.8')
                    }
                }
            },
            {
                'device_id': 'garden-west-002',
                'timestamp': '2023-07-15T18:45:00Z',  # Evening, different device
                'family': 'Sphingidae',
                'genus': 'Manduca',
                'species': 'sexta',
                'track_id': 'moth_track_001',
                'location': {'lat': Decimal('40.7130'), 'long': Decimal('-74.0070')},
                'metadata': {
                    'tracking': {
                        'sequence_number': 1,
                        'track_confidence': Decimal('0.78'),
                        'flight_pattern': 'hovering'
                    },
                    'environmental_context': {
                        'weather': 'clear',
                        'light_level': 'dusk'
                    }
                }
            }
        ]
        
        csv_content = csv_utils.generate_complete_csv(tracking_items, 'classification')
        lines = csv_content.split('\n')
        header = lines[0]
        
        # Should include tracking-related columns
        assert 'track_id' in header
        assert 'device_id' in header
        assert 'timestamp' in header
        assert 'latitude' in header
        assert 'longitude' in header
        
        # Should include flattened tracking metadata
        assert 'metadata_tracking_sequence_number' in header
        assert 'metadata_tracking_track_confidence' in header
        assert 'metadata_environmental_context_weather' in header
        
        # Data should support temporal and spatial analysis
        data_rows = [lines[1], lines[2], lines[3]]
        
        # Same track_id should appear in first two rows
        assert 'butterfly_track_001' in data_rows[0]
        assert 'butterfly_track_001' in data_rows[1]
        assert 'moth_track_001' in data_rows[2]
        
        # Timestamps should be preserved for temporal ordering
        assert '2023-07-15T06:30:00Z' in data_rows[0]
        assert '2023-07-15T06:35:00Z' in data_rows[1]
        assert '2023-07-15T18:45:00Z' in data_rows[2]
        
        # Location data should support movement analysis
        assert '40.7128' in data_rows[0]  # Starting position
        assert '40.7129' in data_rows[1]  # Moved position


class TestCSVExportSecurityAndValidationTDD:
    """TDD tests for security and validation aspects of CSV export."""
    
    def test_csv_export_prevents_csv_injection_attacks(self):
        """Test that CSV export properly escapes potentially malicious CSV content."""
        # Items with content that could be used for CSV injection attacks
        malicious_items = [
            {
                'device_id': '=cmd|"/c calc.exe"!A1',  # Excel formula injection
                'family': '+cmd|"/c calc.exe"!A1',
                'genus': '-cmd|"/c calc.exe"!A1',
                'species': '@sum(1+1)',
                'metadata': {
                    'notes': '=1+1+cmd|"/c calc.exe"!A1',
                    'description': '+1-1*cmd|"/c calc.exe"!A1'
                }
            },
            {
                'device_id': 'normal-device',
                'family': '=HYPERLINK("http://evil.com","Click me")',
                'genus': '=1+1',  # Innocent formula
                'species': '+normal_species_name',  # Starts with + but innocent
                'metadata': {
                    'camera_settings': '=SUM(A1:A10)',
                    'processing_info': '-setting_value'
                }
            }
        ]
        
        csv_content = csv_utils.generate_complete_csv(malicious_items, 'classification')
        
        # CSV should be generated without errors
        lines = csv_content.split('\n')
        assert len(lines) == 3  # Header + 2 data rows
        
        # Potentially dangerous content should be escaped or made safe
        csv_str = str(csv_content)
        
        # Excel formula prefixes should be escaped or handled
        # The exact escaping method may vary, but should not execute as formulas
        data_row_1 = lines[1]
        data_row_2 = lines[2]
        
        # Content should be present but not executable as formulas
        assert 'cmd' in csv_str  # Content preserved
        assert 'calc.exe' in csv_str  # Content preserved
        
        # But when parsed as CSV, should not start with dangerous characters unescaped
        import csv
        import io
        
        csv_file = io.StringIO(csv_content)
        reader = csv.reader(csv_file)
        rows = list(reader)
        
        # Parse the data rows
        header = rows[0]
        parsed_data_1 = rows[1]
        parsed_data_2 = rows[2]
        
        device_id_idx = header.index('device_id')
        
        # Parsed values should not start with formula characters in a dangerous way
        device_id_1 = parsed_data_1[device_id_idx]
        device_id_2 = parsed_data_2[device_id_idx]
        
        # First device_id originally started with =, should be made safe
        if device_id_1.startswith('='):
            # If not escaped, this could be a security issue
            # Implementation should escape or prefix with ' to make safe
            assert False, "CSV injection vulnerability: = not escaped"
    
    def test_csv_export_handles_extremely_long_field_values(self):
        """Test CSV export handles extremely long field values without breaking."""
        # Create items with very long field values
        very_long_string = 'A' * 100000  # 100k characters
        extremely_long_json = json.dumps({f'key_{i}': f'value_{i}' * 1000 for i in range(100)})
        
        items_with_long_values = [
            {
                'device_id': 'test-device',
                'family': very_long_string,
                'genus': 'Normal genus',
                'species': 'normal_species',
                'metadata': {
                    'very_long_description': very_long_string,
                    'complex_data': json.loads(extremely_long_json) if len(extremely_long_json) < 200000 else {},
                    'normal_field': 'normal value'
                },
                'classification_data': {
                    'family': [
                        {'name': very_long_string[:1000], 'confidence': Decimal('0.95')},  # Truncate for reasonableness
                        {'name': 'Normal family name', 'confidence': Decimal('0.05')}
                    ]
                }
            }
        ]
        
        # Should not fail with long values
        csv_content = csv_utils.generate_complete_csv(items_with_long_values, 'classification')
        
        assert len(csv_content) > 0
        
        lines = csv_content.split('\n')
        assert len(lines) == 2  # Header + 1 data row
        
        # Long content should be preserved (or reasonably truncated)
        data_row = lines[1]
        assert 'AAAAA' in data_row  # Part of the long string
        
        # Should still be valid CSV despite long values
        import csv
        import io
        
        csv_file = io.StringIO(csv_content)
        reader = csv.reader(csv_file)
        rows = list(reader)
        
        assert len(rows) == 2
        assert len(rows[1]) == len(rows[0])  # Same number of columns
    
    def test_csv_export_input_sanitization_comprehensive(self):
        """Test comprehensive input sanitization for various attack vectors."""
        # Items with various potentially problematic inputs
        problematic_items = [
            {
                'device_id': 'device"with"quotes',
                'family': 'family,with,commas',
                'genus': 'genus\nwith\nnewlines',
                'species': 'species\twith\ttabs',
                'metadata': {
                    'field_with_nulls': 'value\x00with\x00nulls',
                    'field_with_controls': 'value\x01\x02\x03controls',
                    'field_with_unicode_controls': 'value\u2028\u2029separators',
                    'script_tag': '<script>alert("xss")</script>',
                    'sql_injection': "'; DROP TABLE classifications; --",
                    'html_entities': '&lt;tag&gt;content&amp;stuff'
                }
            }
        ]
        
        csv_content = csv_utils.generate_complete_csv(problematic_items, 'classification')
        
        # Should generate valid CSV
        lines = csv_content.split('\n')
        assert len(lines) == 2
        
        # Should be parseable as CSV
        import csv
        import io
        
        csv_file = io.StringIO(csv_content)
        reader = csv.reader(csv_file)
        rows = list(reader)
        
        assert len(rows) == 2
        header = rows[0]
        data = rows[1]
        
        # Find specific field indices
        device_id_idx = header.index('device_id')
        family_idx = header.index('family')
        genus_idx = header.index('genus')
        
        # Content should be preserved but made CSV-safe
        assert 'device' in data[device_id_idx]
        assert 'quotes' in data[device_id_idx]
        
        assert 'family' in data[family_idx]
        assert 'commas' in data[family_idx]
        
        assert 'genus' in data[genus_idx]
        assert 'newlines' in data[genus_idx]
        
        # Metadata should be flattened and sanitized
        csv_str = str(csv_content)
        assert 'script' in csv_str  # Content preserved
        assert 'DROP TABLE' in csv_str  # Content preserved
        
        # But should not cause CSV parsing issues
        assert len(data) == len(header)  # Columns match


if __name__ == '__main__':
    pytest.main([__file__, '-v'])