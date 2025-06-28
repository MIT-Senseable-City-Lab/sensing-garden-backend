#!/bin/bash
# Script to check if tests would pass in local environment

echo "=== Checking Test Prerequisites ==="
echo ""

# Check Python
echo "1. Python version:"
python3 --version

# Check test dependencies
echo ""
echo "2. Checking test dependencies:"
for dep in pytest pytest-mock pytest-cov moto boto3 flask; do
    if python3 -c "import $dep" 2>/dev/null; then
        echo "   ✓ $dep installed"
    else
        echo "   ✗ $dep NOT installed"
        echo "     Install with: pip install $dep"
    fi
done

# Check if LocalStack would be available
echo ""
echo "3. Docker status:"
if docker info > /dev/null 2>&1; then
    echo "   ✓ Docker is running"
else
    echo "   ✗ Docker is not running"
fi

# Check test files
echo ""
echo "4. Test files:"
for file in tests/__init__.py tests/conftest.py tests/test_handler.py tests/test_dynamodb.py tests/test_integration.py; do
    if [ -f "$file" ]; then
        echo "   ✓ $file exists"
    else
        echo "   ✗ $file missing"
    fi
done

# Check configuration
echo ""
echo "5. Configuration test:"
ENVIRONMENT=local python3 test_local_config.py

echo ""
echo "=== Test Readiness Summary ==="
echo ""
echo "To run tests successfully:"
echo "1. Install dependencies: pip install -r requirements-dev.txt"
echo "2. Start LocalStack: docker-compose up -d localstack"
echo "3. Initialize resources: docker-compose run --rm setup"
echo "4. Run tests: make test"
echo ""
echo "Or use the all-in-one command: make start-local (in one terminal)"
echo "Then in another terminal: make test"