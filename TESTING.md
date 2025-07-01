# Testing Guide

This guide explains the comprehensive test suite for the Sensing Garden backend.

## Overview

The test suite provides full regression confidence by testing:
- All Lambda function handlers (API endpoints)
- DynamoDB operations (CRUD, queries, pagination)
- S3 operations (image/video storage)
- Authentication and authorization
- Input validation and error handling
- Integration workflows

## Test Structure

```
tests/
├── __init__.py
├── conftest.py          # Pytest configuration and fixtures
├── test_handler.py      # API endpoint tests
├── test_dynamodb.py     # Database operation tests
└── test_integration.py  # End-to-end workflow tests
```

## Running Tests

### Prerequisites

Install test dependencies:
```bash
poetry install
```

Or with Homebrew and pip:
```bash
brew install python@3.9
pip3 install pytest pytest-mock pytest-cov moto
```

### Quick Test Run

1. **Start local environment**:
   ```bash
   make start-local
   ```

2. **Run all tests**:
   ```bash
   ./run_tests.sh
   ```

### Manual Test Execution

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_handler.py -v

# Run specific test
python -m pytest tests/test_handler.py::TestClassificationEndpoints::test_post_classification_with_arrays -v

# Run with coverage
python -m pytest tests/ --cov=lambda/src --cov-report=html
```

## Test Categories

### 1. Handler Tests (`test_handler.py`)

Tests all API endpoints:
- **Device endpoints**: POST/GET/DELETE /devices
- **Classification endpoints**: POST/GET /classifications
- **Detection endpoints**: POST/GET /detections  
- **Model endpoints**: POST/GET /models
- **Video endpoints**: POST/GET /videos
- **Count endpoints**: GET /*/count
- **Error handling**: Invalid JSON, missing fields, unknown endpoints

### 2. DynamoDB Tests (`test_dynamodb.py`)

Tests database operations:
- **CRUD operations**: Create, read, update, delete
- **Query operations**: Time ranges, pagination, filtering
- **Data validation**: Schema validation, required fields
- **Special features**: Confidence arrays, metadata handling
- **Count operations**: Efficient counting without full scans

### 3. Integration Tests (`test_integration.py`)

Tests complete workflows:
- **Device lifecycle**: Create device → Upload data → Query → Delete
- **Multi-device tracking**: Multiple devices with different data
- **Time series data**: Proper ordering and time-based queries
- **Model versioning**: Different model versions
- **Video workflows**: Registration and retrieval
- **Error recovery**: System behavior under error conditions

## Test Data

Tests use isolated test data:
- Device IDs: `test-device-001`, `test-device-002`, etc.
- Test images: Base64-encoded 1x1 PNG
- S3 buckets: `test-sensing-garden-images`, `test-sensing-garden-videos`
- No production data is ever accessed

## Coverage Goals

The test suite aims for:
- **100% coverage** of Lambda handlers
- **100% coverage** of DynamoDB operations
- **100% coverage** of validation logic
- **Key integration paths** fully tested

Current coverage can be viewed by running tests with coverage and opening `coverage_html/index.html`.

## Writing New Tests

When adding new features:

1. **Add handler tests** for new endpoints
2. **Add DynamoDB tests** for new data operations
3. **Add integration tests** for new workflows
4. **Update fixtures** if new test data is needed

Example test structure:
```python
def test_new_feature(self, api_event, lambda_context, dynamodb_tables):
    """Test description"""
    # Arrange
    test_data = {...}
    
    # Act
    event = api_event('POST', '/endpoint', body=json.dumps(test_data))
    response = lambda_handler(event, lambda_context)
    
    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['expected_field'] == 'expected_value'
```

## Continuous Integration

The test suite is designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Start LocalStack
  run: docker-compose up -d localstack

- name: Wait for LocalStack
  run: sleep 5

- name: Run tests
  run: ./run_tests.sh
```

## Troubleshooting

### Common Issues

1. **LocalStack not running**
   ```bash
   make start-local  # Start LocalStack first
   ```

2. **Import errors**
   ```bash
   poetry install  # Install dependencies
   ```

3. **Permission denied**
   ```bash
   chmod +x run_tests.sh  # Make script executable
   ```

4. **Tests hanging**
   - Check LocalStack logs: `docker-compose logs localstack`
   - Ensure no port conflicts on 4566

### Debug Mode

Run tests with print output:
```bash
python -m pytest tests/ -v -s
```

## Safety Guarantees

The test suite ensures:
- ✅ No production resources accessed
- ✅ All tests run locally
- ✅ Isolated test data
- ✅ Automatic cleanup after tests
- ✅ Safe to run repeatedly

## Next Steps

After tests pass locally:
1. Create pull request with changes
2. CI/CD runs tests automatically
3. Manual review of code changes
4. Deploy to staging (if available)
5. Deploy to production with confidence