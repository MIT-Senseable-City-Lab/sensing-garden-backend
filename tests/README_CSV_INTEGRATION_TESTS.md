# CSV Export Integration Tests

This directory contains real integration tests for the CSV export functionality that test against the actual deployed AWS infrastructure.

## Test Files

- **`test_csv_export_integration_real.py`** - Comprehensive integration tests for the `/export` endpoint against real deployed API

## Purpose

These tests are designed to:

1. **Test against actual deployed infrastructure** - No mocks, real HTTP requests to deployed API Gateway
2. **Validate API contract** - Ensure the `/export` endpoint works as expected when implemented
3. **Demonstrate expected failures** - Show what's currently missing from the infrastructure
4. **Test comprehensive scenarios** - Cover all table types, error handling, authentication, etc.

## Current Status

**Expected Behavior**: Most tests will FAIL or SKIP initially because:
- The `/export` endpoint is implemented in the Lambda handler code but not configured in terraform routes
- Tests are written to expect success once the terraform route is added
- This demonstrates the gap between implementation and infrastructure configuration

## Test Configuration

The tests use these real deployed endpoints:

- **API Base URL**: `https://nxdp0npcb2.execute-api.us-east-1.amazonaws.com`
- **API Key**: Retrieved from terraform outputs (`terraform output test_api_key`)
- **Authentication**: Uses X-Api-Key header with real API key

## Running the Tests

### Prerequisites

1. Install dependencies:
   ```bash
   poetry install
   ```

2. Ensure you have access to the deployed infrastructure (API key working)

### Basic Test Execution

Run all integration tests:
```bash
poetry run pytest tests/test_csv_export_integration_real.py -v
```

Run a specific test:
```bash
poetry run pytest tests/test_csv_export_integration_real.py::TestCSVExportIntegrationReal::test_export_endpoint_exists -v
```

### Test Categories

**1. Endpoint Existence Test**
```bash
poetry run pytest tests/test_csv_export_integration_real.py::TestCSVExportIntegrationReal::test_export_endpoint_exists -v
```
- Tests that the `/export` endpoint exists
- **Currently FAILS** with 404 because terraform route is missing

**2. Table-Specific Export Tests**
```bash
poetry run pytest tests/test_csv_export_integration_real.py -k "test_export_detections_csv or test_export_classifications_csv" -v
```
- Tests CSV export for each table type: detections, classifications, environment, devices, models, videos
- **Currently SKIP** due to missing endpoint

**3. Parameter and Filter Tests**
```bash
poetry run pytest tests/test_csv_export_integration_real.py -k "test_export_with_date_range or test_export_with_device_filter" -v
```
- Tests date range filtering, device filtering, limit parameters
- **Currently SKIP** due to missing endpoint

**4. Error Handling Tests**
```bash
poetry run pytest tests/test_csv_export_integration_real.py -k "test_export_error" -v
```
- Tests invalid parameters, authentication, error responses
- **Currently SKIP** due to missing endpoint

**5. Data-Dependent Tests**
```bash
RUN_DATA_DEPENDENT_TESTS=1 poetry run pytest tests/test_csv_export_integration_real.py::TestCSVExportIntegrationRealWithData -v
```
- Tests that require actual data in the system
- Set environment variable to enable these tests

## Expected Test Results

### Current State (Before Infrastructure Fix)

```
FAILED tests/...::test_export_endpoint_exists - AssertionError: EXPECTED FAILURE: /export endpoint not implemented yet. Got 404
SKIPPED [15 tests] - Export endpoint not implemented yet: 404
```

### After Adding Terraform Route

Once the `/export` route is added to terraform `api_gateway.tf`:

```terraform
resource "aws_apigatewayv2_route" "get_export" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /export"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}
```

The tests should start passing and provide comprehensive validation of the CSV export functionality.

## Test Coverage

The integration tests cover:

**Functional Tests:**
- ✅ All table types: detections, classifications, environment, devices, models, videos
- ✅ Date range filtering (start_time, end_time)
- ✅ Device filtering (device_id parameter)
- ✅ Limit parameter handling
- ✅ Custom filename specification
- ✅ Automatic filename generation
- ✅ CSV format validation
- ✅ Response header validation

**Error Handling Tests:**
- ✅ Invalid table parameter
- ✅ Missing required parameters
- ✅ Invalid date formats
- ✅ Authentication requirements
- ✅ Large limit handling
- ✅ Network error resilience (with retry logic)

**Real Data Tests:**
- ✅ Export with actual system data
- ✅ CSV content validation
- ✅ Data filtering verification

## Infrastructure Requirements

For these tests to pass, the following infrastructure must be in place:

1. **API Gateway Route**: `GET /export` route configured in terraform
2. **Lambda Handler**: `/export` endpoint implementation (✅ already exists)
3. **CSV Utils**: CSV formatting utilities (✅ already exists)
4. **Database Access**: DynamoDB query permissions (✅ already exists)
5. **Authentication**: API key validation (✅ already exists)

## Debugging Failed Tests

**404 Errors**: Endpoint not configured in terraform API Gateway routes
**401/403 Errors**: Authentication/API key issues
**500 Errors**: Lambda function errors (check CloudWatch logs)
**Connection Errors**: Network issues or incorrect base URL

## Continuous Integration

These tests can be integrated into CI/CD pipelines to:
- Validate infrastructure deployments
- Ensure CSV export functionality remains working
- Test against real deployed environments
- Catch regressions in API functionality

## Security Considerations

- Tests use real API keys from terraform outputs
- API keys are not hardcoded in test files
- Tests connect to real AWS resources
- Ensure test environment is isolated from production data