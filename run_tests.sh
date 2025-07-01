#!/bin/bash
# Test runner script for sensing-garden-backend

echo "=== Sensing Garden Backend Test Suite ==="
echo ""

# Check if local environment is running
echo "Checking local environment..."
if ! curl -s http://localhost:4566/_localstack/health > /dev/null 2>&1; then
    echo "❌ LocalStack is not running!"
    echo "Please start the local environment with: make start-local"
    exit 1
fi

echo "✓ LocalStack is running"
echo ""

# Set environment for tests
export ENVIRONMENT=local
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

# Run tests with coverage
echo "Running tests with coverage..."
echo ""

python -m pytest tests/ \
    -v \
    --cov=lambda/src \
    --cov-report=term-missing \
    --cov-report=html:coverage_html \
    -W ignore::DeprecationWarning

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
    echo ""
    echo "Coverage report available at: coverage_html/index.html"
else
    echo ""
    echo "❌ Some tests failed!"
    exit 1
fi