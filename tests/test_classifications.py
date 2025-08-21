"""
Tests for classification endpoint with environment data support.
"""
import pytest
import json
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, Mock

import handler


class TestClassificationEnvironmentData:
    """Test classification endpoint with environment data parameters."""

    def test_basic_classification_without_environment_data(self, basic_classification_data, mock_s3, mock_dynamodb):
        """Test that basic classification still works without environment data (backward compatibility)."""
        # Mock image upload and DynamoDB storage functions
        with patch('handler._upload_image_to_s3') as mock_upload, \
             patch('handler.dynamodb.store_classification_data') as mock_store:
            
            mock_upload.return_value = "test-image-key.jpg"
            mock_store.return_value = {}
            
            result = handler._store_classification(basic_classification_data)
            
        # Verify response
        assert result['statusCode'] == 200
        response_data = json.loads(result['body'])
        assert response_data['message'] == 'Classification data stored successfully'
        assert 'data' in response_data
        
        stored_data = response_data['data']
        assert stored_data['device_id'] == basic_classification_data['device_id']
        assert stored_data['family'] == basic_classification_data['family']
        assert stored_data['genus'] == basic_classification_data['genus']
        assert stored_data['species'] == basic_classification_data['species']
        
        # Verify no environment data is present
        assert 'location' not in stored_data
        assert 'temperature' not in stored_data
        assert 'humidity' not in stored_data
        assert 'pm1p0' not in stored_data

        # Verify DynamoDB store function was called
        mock_store.assert_called_once()
        call_args = mock_store.call_args[0][0]  # First argument to store_classification_data
        assert call_args['device_id'] == basic_classification_data['device_id']

    def test_classification_with_full_environment_data(self, classification_with_environment, mock_s3, mock_dynamodb):
        """Test classification with complete environment and location data."""
        # Mock image upload and DynamoDB storage functions
        with patch('handler._upload_image_to_s3') as mock_upload, \
             patch('handler.dynamodb.store_classification_data') as mock_store:
            
            mock_upload.return_value = "test-image-key.jpg"
            mock_store.return_value = {}
            
            result = handler._store_classification(classification_with_environment)
            
        # Verify response
        assert result['statusCode'] == 200
        response_data = json.loads(result['body'])
        assert response_data['message'] == 'Classification data stored successfully'
        
        stored_data = response_data['data']
        
        # Verify basic classification data
        assert stored_data['device_id'] == classification_with_environment['device_id']
        assert stored_data['family'] == classification_with_environment['family']
        
        # Verify location data is present and converted
        assert 'location' in stored_data
        location = stored_data['location']
        assert float(location['lat']) == classification_with_environment['location']['lat']
        assert float(location['long']) == classification_with_environment['location']['long']
        assert float(location['alt']) == classification_with_environment['location']['alt']
        
        # Verify environmental data is present with correct field mapping
        assert stored_data['temperature'] == classification_with_environment['data']['ambient_temperature']
        assert stored_data['humidity'] == classification_with_environment['data']['ambient_humidity']
        assert stored_data['pm1p0'] == classification_with_environment['data']['pm1p0']
        assert stored_data['pm2p5'] == classification_with_environment['data']['pm2p5']
        assert stored_data['pm4p0'] == classification_with_environment['data']['pm4p0']
        assert stored_data['pm10p0'] == classification_with_environment['data']['pm10p0']
        assert stored_data['voc_index'] == classification_with_environment['data']['voc_index']
        assert stored_data['nox_index'] == classification_with_environment['data']['nox_index']
        
        # Verify additional fields
        assert stored_data['track_id'] == classification_with_environment['track_id']

        # Verify DynamoDB store function was called with correct data types
        mock_store.assert_called_once()
        call_args = mock_store.call_args[0][0]  # First argument to store_classification_data
        
        # Check that environmental data was converted to Decimal
        assert isinstance(call_args['temperature'], Decimal)
        assert isinstance(call_args['humidity'], Decimal)
        assert isinstance(call_args['pm1p0'], Decimal)
        assert isinstance(call_args['location']['lat'], Decimal)
        assert isinstance(call_args['location']['long'], Decimal)

    def test_classification_with_location_only(self, basic_classification_data, location_data, mock_s3, mock_dynamodb):
        """Test classification with location data but no environmental sensor data."""
        # Add location to basic classification data
        classification_data = basic_classification_data.copy()
        classification_data['location'] = location_data
        
        # Mock image upload and DynamoDB storage functions
        with patch('handler._upload_image_to_s3') as mock_upload, \
             patch('handler.dynamodb.store_classification_data') as mock_store:
            
            mock_upload.return_value = "test-image-key.jpg"
            mock_store.return_value = {}
            
            result = handler._store_classification(classification_data)
            
        # Verify response
        assert result['statusCode'] == 200
        response_data = json.loads(result['body'])
        stored_data = response_data['data']
        
        # Verify location data is present
        assert 'location' in stored_data
        location = stored_data['location']
        assert float(location['lat']) == location_data['lat']
        assert float(location['long']) == location_data['long']
        assert float(location['alt']) == location_data['alt']
        
        # Verify environmental sensor data is NOT present
        assert 'temperature' not in stored_data
        assert 'humidity' not in stored_data
        assert 'pm1p0' not in stored_data

    def test_classification_with_partial_environment_data(self, basic_classification_data, mock_s3, mock_dynamodb):
        """Test classification with partial environmental data."""
        # Add partial environmental data
        classification_data = basic_classification_data.copy()
        classification_data['data'] = {
            'pm1p0': 15.2,
            'pm2p5': 22.8,
            'ambient_temperature': 25.5
            # Missing other environmental fields
        }
        
        # Mock image upload and DynamoDB storage functions
        with patch('handler._upload_image_to_s3') as mock_upload, \
             patch('handler.dynamodb.store_classification_data') as mock_store:
            
            mock_upload.return_value = "test-image-key.jpg"
            mock_store.return_value = {}
            
            result = handler._store_classification(classification_data)
            
        # Verify response
        assert result['statusCode'] == 200
        response_data = json.loads(result['body'])
        stored_data = response_data['data']
        
        # Verify only provided environmental data is present
        assert stored_data['pm1p0'] == 15.2
        assert stored_data['pm2p5'] == 22.8
        assert stored_data['temperature'] == 25.5  # ambient_temperature mapped to temperature
        
        # Verify missing fields are not present
        assert 'humidity' not in stored_data
        assert 'pm4p0' not in stored_data
        assert 'voc_index' not in stored_data

    def test_invalid_location_data_missing_required_fields(self, basic_classification_data, mock_s3):
        """Test validation error when location data is missing required fields."""
        # Add invalid location data (missing required lat/long)
        classification_data = basic_classification_data.copy()
        classification_data['location'] = {
            'alt': 10.5  # Missing required lat and long
        }
        
        with patch('handler._upload_image_to_s3') as mock_upload:
            mock_upload.return_value = "test-image-key.jpg"
            
            with pytest.raises(ValueError) as exc_info:
                handler._store_classification(classification_data)
            
            assert "location must contain required fields: lat, long" in str(exc_info.value)

    def test_invalid_location_data_not_dict(self, basic_classification_data, mock_s3):
        """Test validation error when location data is not a dictionary."""
        # Add invalid location data (not a dict)
        classification_data = basic_classification_data.copy()
        classification_data['location'] = "invalid_location_string"
        
        with patch('handler._upload_image_to_s3') as mock_upload:
            mock_upload.return_value = "test-image-key.jpg"
            
            with pytest.raises(ValueError) as exc_info:
                handler._store_classification(classification_data)
            
            assert "location must be an object (dict) if provided" in str(exc_info.value)

    def test_invalid_environment_data_not_dict(self, basic_classification_data, mock_s3):
        """Test validation error when environment data is not a dictionary."""
        # Add invalid environmental data (not a dict)
        classification_data = basic_classification_data.copy()
        classification_data['data'] = "invalid_env_string"
        
        with patch('handler._upload_image_to_s3') as mock_upload:
            mock_upload.return_value = "test-image-key.jpg"
            
            with pytest.raises(ValueError) as exc_info:
                handler._store_classification(classification_data)
            
            assert "data must be an object (dict) if provided" in str(exc_info.value)

    def test_invalid_environment_data_non_numeric_values(self, basic_classification_data, mock_s3):
        """Test validation error when environment data contains non-numeric values."""
        # Add environmental data with invalid (non-numeric) values
        classification_data = basic_classification_data.copy()
        classification_data['data'] = {
            'pm1p0': "not_a_number",
            'ambient_temperature': 23.4
        }
        
        with patch('handler._upload_image_to_s3') as mock_upload:
            mock_upload.return_value = "test-image-key.jpg"
            
            # The code currently raises decimal.InvalidOperation, which is converted to ValueError
            # in the handler's try-catch block. Let's test for the actual error that gets raised.
            from decimal import InvalidOperation
            with pytest.raises(InvalidOperation):
                handler._store_classification(classification_data)

    def test_environment_data_field_mapping(self, basic_classification_data, mock_s3, mock_dynamodb):
        """Test that environment data fields are correctly mapped from API to database format."""
        # Add environmental data
        classification_data = basic_classification_data.copy()
        classification_data['data'] = {
            'ambient_temperature': 24.7,
            'ambient_humidity': 68.3,
            'pm1p0': 11.2,
            'voc_index': 145
        }
        
        # Mock image upload and DynamoDB storage functions
        with patch('handler._upload_image_to_s3') as mock_upload, \
             patch('handler.dynamodb.store_classification_data') as mock_store:
            
            mock_upload.return_value = "test-image-key.jpg"
            mock_store.return_value = {}
            
            result = handler._store_classification(classification_data)
            
        # Verify DynamoDB store function was called with correctly mapped fields
        mock_store.assert_called_once()
        call_args = mock_store.call_args[0][0]  # First argument to store_classification_data
        
        # Verify field mapping: ambient_temperature -> temperature, ambient_humidity -> humidity
        assert call_args['temperature'] == Decimal('24.7')
        assert call_args['humidity'] == Decimal('68.3')
        assert call_args['pm1p0'] == Decimal('11.2')
        assert call_args['voc_index'] == Decimal('145')
        
        # Verify original field names are NOT stored
        assert 'ambient_temperature' not in call_args
        assert 'ambient_humidity' not in call_args

    def test_decimal_conversion_for_dynamodb(self, classification_with_environment, mock_s3, mock_dynamodb):
        """Test that all numeric values are properly converted to Decimal for DynamoDB storage."""
        # Mock image upload and DynamoDB storage functions
        with patch('handler._upload_image_to_s3') as mock_upload, \
             patch('handler.dynamodb.store_classification_data') as mock_store:
            
            mock_upload.return_value = "test-image-key.jpg"
            mock_store.return_value = {}
            
            handler._store_classification(classification_with_environment)
            
        # Verify DynamoDB store function was called with Decimal values
        mock_store.assert_called_once()
        call_args = mock_store.call_args[0][0]  # First argument to store_classification_data
        
        # Check confidence scores (existing functionality)
        assert isinstance(call_args['family_confidence'], Decimal)
        assert isinstance(call_args['genus_confidence'], Decimal)
        assert isinstance(call_args['species_confidence'], Decimal)
        
        # Check environmental data (new functionality)
        assert isinstance(call_args['temperature'], Decimal)
        assert isinstance(call_args['humidity'], Decimal)
        assert isinstance(call_args['pm1p0'], Decimal)
        assert isinstance(call_args['pm2p5'], Decimal)
        assert isinstance(call_args['voc_index'], Decimal)
        assert isinstance(call_args['nox_index'], Decimal)
        
        # Check location data
        assert isinstance(call_args['location']['lat'], Decimal)
        assert isinstance(call_args['location']['long'], Decimal)
        assert isinstance(call_args['location']['alt'], Decimal)
        
        # Check bounding box data (existing functionality)
        for coord in call_args['bounding_box']:
            assert isinstance(coord, Decimal)