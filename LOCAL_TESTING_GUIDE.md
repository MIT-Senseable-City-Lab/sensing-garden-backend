# Local Setup Testing Guide

This guide walks through testing every aspect of the local development environment to ensure everything works correctly.

## Quick Verification

Run the automated verification script:
```bash
./verify_local_setup.sh
```

This checks:
- Docker and dependencies
- LocalStack health
- AWS resources (DynamoDB tables, S3 buckets)
- API server
- API endpoints
- Safety isolation
- Confidence arrays
- Test framework

## Step-by-Step Manual Testing

### 1. Initial Setup Verification

```bash
# Check Docker is running
docker info

# Check Python version
python3 --version  # Should be 3.9+

# Check dependencies installed
pip list | grep -E "(boto3|flask|pytest)"
```

### 2. Start Local Environment

```bash
# Terminal 1: Start LocalStack
make start-local

# Wait for "LocalStack is ready!" message
# Then press Ctrl+C to stop the API server

# Terminal 2: Verify LocalStack resources
aws --endpoint-url=http://localhost:4566 dynamodb list-tables
aws --endpoint-url=http://localhost:4566 s3 ls
```

Expected output:
- 5 DynamoDB tables
- 2 S3 buckets (local-sensing-garden-*)

### 3. Test API Server

```bash
# Terminal 1: Start API server only
python run_local.py

# Terminal 2: Test endpoints
# Health check
curl http://localhost:8000/health

# Get devices (should be empty or have test device)
curl http://localhost:8000/devices | jq

# Create a device
curl -X POST http://localhost:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"device_id": "test-device-001", "name": "Test Device"}' | jq

# Get devices again (should show the new device)
curl http://localhost:8000/devices | jq
```

### 4. Test Classification with Arrays

```bash
# Run the confidence array test
python test_confidence_arrays.py
```

This tests:
- Creating classifications with array fields
- Backward compatibility without arrays
- Retrieving data with arrays intact

### 5. Test Complete Workflow

```bash
# Create a complete insect detection workflow

# 1. Create a device
curl -X POST http://localhost:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"device_id": "garden-pi-001"}' | jq

# 2. Post a detection
curl -X POST http://localhost:8000/detections \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "garden-pi-001",
    "model_id": "yolov8-insects",
    "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "confidence": 0.92,
    "object_class": "butterfly",
    "bounding_box": [100, 200, 300, 400]
  }' | jq

# 3. Post a classification with arrays
curl -X POST http://localhost:8000/classifications \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "garden-pi-001",
    "model_id": "insect-classifier-v2",
    "track_id": "track-123",
    "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "family": "Lepidoptera",
    "genus": "Vanessa",
    "species": "Vanessa cardui",
    "family_confidence": 0.95,
    "genus_confidence": 0.87,
    "species_confidence": 0.73,
    "family_confidence_array": [0.95, 0.03, 0.01, 0.01],
    "genus_confidence_array": [0.87, 0.08, 0.03, 0.02],
    "species_confidence_array": [0.73, 0.15, 0.07, 0.05]
  }' | jq

# 4. Query the data
curl "http://localhost:8000/detections?device_id=garden-pi-001" | jq
curl "http://localhost:8000/classifications?device_id=garden-pi-001" | jq

# 5. Check counts
curl "http://localhost:8000/detections/count?device_id=garden-pi-001" | jq
curl "http://localhost:8000/classifications/count?device_id=garden-pi-001" | jq
```

### 6. Run Full Test Suite

```bash
# Run all tests with coverage
make test

# Run specific test categories
make test-quick  # Without coverage
make test-specific TEST=tests/test_handler.py  # Specific file
```

### 7. Verify Production Isolation

```bash
# This should PASS all safety checks
python verify_local_safety.py
```

Output should show:
- ✓ Environment variables correctly configured
- ✓ Cannot access production S3
- ✓ Cannot access production DynamoDB
- ✓ Can access local services

### 8. Check Data Persistence

```bash
# Data persists in LocalStack between API restarts

# 1. Stop API server (Ctrl+C)
# 2. Restart API server
python run_local.py

# 3. Data should still be there
curl http://localhost:8000/devices | jq
```

### 9. Test Error Handling

```bash
# Invalid JSON
curl -X POST http://localhost:8000/devices \
  -H "Content-Type: application/json" \
  -d 'invalid json' | jq

# Missing required fields
curl -X POST http://localhost:8000/classifications \
  -H "Content-Type: application/json" \
  -d '{"device_id": "test"}' | jq

# Invalid confidence array values
curl -X POST http://localhost:8000/classifications \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test",
    "family_confidence_array": "not-an-array"
  }' | jq
```

## Troubleshooting

### LocalStack Issues

```bash
# Check LocalStack logs
docker-compose logs localstack

# Restart LocalStack
docker-compose down
docker-compose up -d localstack

# Re-run setup
docker-compose run --rm setup
```

### API Server Issues

```bash
# Check for port conflicts
lsof -i :8000

# Run with debug output
FLASK_ENV=development python run_local.py
```

### Test Failures

```bash
# Run tests with output
pytest tests/ -v -s

# Check specific test
pytest tests/test_handler.py::TestClassificationEndpoints::test_post_classification_with_arrays -v -s
```

## Expected Results

When everything is working correctly:

1. ✅ LocalStack running with all tables and buckets
2. ✅ API server responding on port 8000
3. ✅ All CRUD operations working
4. ✅ Confidence arrays storing and retrieving correctly
5. ✅ Tests passing with good coverage
6. ✅ Complete isolation from production

## Performance Testing

Test the local environment can handle load:

```bash
# Create multiple devices
for i in {1..10}; do
  curl -X POST http://localhost:8000/devices \
    -H "Content-Type: application/json" \
    -d "{\"device_id\": \"perf-test-$i\"}" &
done
wait

# Verify all created
curl http://localhost:8000/devices | jq '.items | length'
```

## Next Steps

After verification:
1. Start developing new features
2. Run tests before committing
3. Use the local environment for debugging
4. Test API changes without deployment