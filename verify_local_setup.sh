#!/bin/bash
# Comprehensive verification script for local setup

echo "=== Sensing Garden Local Setup Verification ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall status
ALL_GOOD=true

# Function to check status
check_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
        ALL_GOOD=false
    fi
}

echo "1. Checking Docker and dependencies..."
docker --version > /dev/null 2>&1
check_status $? "Docker is installed"

docker-compose --version > /dev/null 2>&1
check_status $? "Docker Compose is installed"

python3 --version > /dev/null 2>&1
check_status $? "Python 3 is installed"

echo ""
echo "2. Checking LocalStack..."
if docker ps | grep -q localstack; then
    echo -e "${GREEN}✓${NC} LocalStack container is running"
    
    # Check LocalStack health
    curl -s http://localhost:4566/_localstack/health > /dev/null 2>&1
    check_status $? "LocalStack is healthy and responding"
else
    echo -e "${RED}✗${NC} LocalStack is not running"
    echo "  Run: make start-local"
    ALL_GOOD=false
fi

echo ""
echo "3. Checking AWS resources in LocalStack..."
if [ "$ALL_GOOD" = true ]; then
    # Check DynamoDB tables
    echo "  DynamoDB tables:"
    tables=$(aws --endpoint-url=http://localhost:4566 dynamodb list-tables --query 'TableNames' --output text 2>/dev/null)
    if [ $? -eq 0 ]; then
        for expected in "sensing-garden-detections" "sensing-garden-devices" "sensing-garden-classifications" "sensing-garden-models" "sensing-garden-videos"; do
            if echo "$tables" | grep -q "$expected"; then
                echo -e "    ${GREEN}✓${NC} $expected"
            else
                echo -e "    ${RED}✗${NC} $expected (missing)"
                ALL_GOOD=false
            fi
        done
    else
        echo -e "    ${RED}✗${NC} Could not list DynamoDB tables"
        ALL_GOOD=false
    fi
    
    # Check S3 buckets
    echo "  S3 buckets:"
    buckets=$(aws --endpoint-url=http://localhost:4566 s3 ls 2>/dev/null | awk '{print $3}')
    if [ $? -eq 0 ]; then
        for expected in "local-sensing-garden-images" "local-sensing-garden-videos"; do
            if echo "$buckets" | grep -q "$expected"; then
                echo -e "    ${GREEN}✓${NC} $expected"
            else
                echo -e "    ${RED}✗${NC} $expected (missing)"
                ALL_GOOD=false
            fi
        done
    else
        echo -e "    ${RED}✗${NC} Could not list S3 buckets"
        ALL_GOOD=false
    fi
fi

echo ""
echo "4. Checking local API server..."
# Try to hit the health endpoint
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✓${NC} Local API server is running on port 8000"
    
    # Get health check response
    health=$(curl -s http://localhost:8000/health 2>/dev/null)
    echo "  Response: $health"
else
    echo -e "${YELLOW}!${NC} Local API server is not running"
    echo "  This is expected if you haven't started it yet"
    echo "  Run: python run_local.py"
fi

echo ""
echo "5. Testing API endpoints..."
if [ "$response" = "200" ]; then
    # Test GET devices
    echo "  Testing GET /devices..."
    devices=$(curl -s http://localhost:8000/devices 2>/dev/null)
    if echo "$devices" | grep -q "items"; then
        echo -e "    ${GREEN}✓${NC} GET /devices works"
    else
        echo -e "    ${RED}✗${NC} GET /devices failed"
        ALL_GOOD=false
    fi
    
    # Test POST device
    echo "  Testing POST /devices..."
    post_result=$(curl -s -X POST http://localhost:8000/devices \
        -H "Content-Type: application/json" \
        -d '{"device_id": "verify-test-device"}' 2>/dev/null)
    if echo "$post_result" | grep -q "Device added"; then
        echo -e "    ${GREEN}✓${NC} POST /devices works"
        
        # Clean up test device
        curl -s -X DELETE "http://localhost:8000/devices?device_id=verify-test-device" > /dev/null 2>&1
    else
        echo -e "    ${RED}✗${NC} POST /devices failed"
        ALL_GOOD=false
    fi
fi

echo ""
echo "6. Running safety verification..."
if [ -f verify_local_safety.py ]; then
    python verify_local_safety.py > /dev/null 2>&1
    check_status $? "Local environment is safely isolated from production"
else
    echo -e "${YELLOW}!${NC} Safety verification script not found"
fi

echo ""
echo "7. Testing confidence arrays..."
if [ "$response" = "200" ] && [ -f test_confidence_arrays.py ]; then
    echo "  Running confidence array tests..."
    python test_confidence_arrays.py > /tmp/confidence_test.log 2>&1
    if [ $? -eq 0 ]; then
        echo -e "    ${GREEN}✓${NC} Confidence array implementation works"
    else
        echo -e "    ${RED}✗${NC} Confidence array tests failed"
        echo "  Check /tmp/confidence_test.log for details"
        ALL_GOOD=false
    fi
fi

echo ""
echo "8. Running quick test suite..."
if [ -d tests ] && command -v pytest > /dev/null 2>&1; then
    echo "  Running a sample test..."
    ENVIRONMENT=local AWS_ENDPOINT_URL=http://localhost:4566 \
        python -m pytest tests/test_handler.py::TestDeviceEndpoints::test_get_devices_empty -v > /tmp/pytest.log 2>&1
    if [ $? -eq 0 ]; then
        echo -e "    ${GREEN}✓${NC} Test framework is working"
    else
        echo -e "    ${RED}✗${NC} Test framework has issues"
        echo "  Check /tmp/pytest.log for details"
        ALL_GOOD=false
    fi
else
    echo -e "${YELLOW}!${NC} Test suite not set up yet"
    echo "  Run: poetry install"
fi

echo ""
echo "============================================="
if [ "$ALL_GOOD" = true ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    echo ""
    echo "Your local environment is fully set up and working correctly."
    echo ""
    echo "Next steps:"
    echo "1. Run the full test suite: make test"
    echo "2. Start developing with confidence!"
else
    echo -e "${RED}❌ Some checks failed${NC}"
    echo ""
    echo "Please fix the issues above and run this script again."
    echo ""
    echo "Common fixes:"
    echo "- Start LocalStack: make start-local"
    echo "- Install dependencies: poetry install"
    echo "- Check Docker is running"
fi

echo "============================================="