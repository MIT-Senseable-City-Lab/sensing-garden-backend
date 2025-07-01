# Unified Testing Framework

This document describes the unified testing framework for the Sensing Garden backend.

## Overview

We use **pytest** as our testing framework with comprehensive test coverage for:
- Unit tests for individual functions
- Integration tests for API workflows  
- Regression tests to catch bugs
- CI/CD pipeline for automated testing on PRs

## Test Structure

```
tests/
├── __init__.py          # Test package marker
├── conftest.py          # Shared fixtures and configuration
├── test_handler.py      # API endpoint tests
├── test_dynamodb.py     # Database operation tests
└── test_integration.py  # End-to-end workflow tests
```

## Configuration

### pytest.ini
Centralized pytest configuration with:
- Test discovery settings
- Coverage requirements (80% minimum)
- Environment variables for local testing
- Test markers for organization
- Timeout settings

### GitHub Actions (.github/workflows/test.yml)
Automated testing on every PR with:
- LocalStack setup
- Full test suite execution
- Coverage reporting
- Linting checks

## Running Tests

### Locally
```bash
# Full test suite with coverage
make test

# Quick tests without coverage
pytest tests/ -v

# Specific test file
pytest tests/test_handler.py -v

# Specific test function
pytest tests/test_handler.py::TestClassificationEndpoints::test_post_classification_with_arrays -v
```

### In CI/CD
Tests run automatically on:
- Every push to main or develop
- Every pull request to main
- Using the same LocalStack setup as local development

## Test Coverage

Current coverage requirements:
- **Minimum 80%** overall coverage
- Coverage reports in multiple formats:
  - Terminal output
  - HTML report (coverage_html/)
  - XML for CI integration

## Regression Testing

Our tests catch regressions by:
1. Testing all API responses thoroughly
2. Verifying data structure integrity
3. Checking edge cases and error conditions

Example of regression detection:
```python
# Test sends confidence arrays
response = api_call('/classifications', {
    'family_confidence_array': [0.95, 0.03, 0.02]
})

# Test verifies correct field in response
assert 'family_confidence_array' in response['data']
# If code stores as wrong field name, test fails ✓
```

## Test Dependencies

Required packages (installed via poetry install):
- pytest: Core testing framework
- pytest-cov: Coverage reporting
- pytest-env: Environment variable handling
- pytest-timeout: Test timeouts
- pytest-mock: Mocking support
- moto: AWS service mocking
- flask: Local API server
- boto3: AWS SDK

## Best Practices

1. **Write tests for new features**: Every new endpoint or function needs tests
2. **Test edge cases**: Invalid inputs, missing fields, large data
3. **Use fixtures**: Share common setup via conftest.py
4. **Mock external services**: Use moto for AWS services
5. **Keep tests fast**: Use timeouts, avoid slow operations
6. **Clear test names**: `test_<what>_<condition>_<expected_result>`

## Debugging Failed Tests

```bash
# Run with output
pytest tests/ -v -s

# Run with full traceback
pytest tests/ -v --tb=long

# Run specific test with debugging
pytest tests/test_handler.py::test_name -v -s --pdb
```

## CI/CD Integration

The GitHub Actions workflow:
1. Sets up Python 3.9
2. Installs dependencies with caching
3. Starts LocalStack
4. Runs all tests with coverage
5. Uploads coverage to Codecov
6. Runs linting checks
7. Fails the PR if tests don't pass

## Maintaining Tests

When changing code:
1. Run tests locally first: `make test`
2. Update tests if API changes
3. Ensure coverage doesn't drop
4. Fix any linting issues
5. Push to PR - CI will verify

## Summary

Our unified testing framework ensures:
- ✅ All code changes are tested
- ✅ Regressions are caught immediately
- ✅ Tests run both locally and in CI
- ✅ Consistent test environment
- ✅ High confidence in deployments