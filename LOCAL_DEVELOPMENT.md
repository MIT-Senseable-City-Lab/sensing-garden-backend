# Local Development Setup

This guide explains how to set up and use the local development environment for the Sensing Garden backend.

## Overview

The local development environment uses LocalStack to simulate AWS services locally, ensuring complete isolation from production resources. This setup allows you to:

- Test Lambda functions locally without deployment
- Use local DynamoDB tables and S3 buckets
- Run tests without touching production data
- Develop and debug with fast iteration cycles

## Prerequisites

Install using Homebrew (recommended for macOS):
```bash
brew install docker
brew install docker-compose
brew install python@3.9
brew install make  # Usually pre-installed on macOS
brew install awscli  # For testing AWS commands locally
```

Manual installation:
- Docker and Docker Compose
- Python 3.9+
- Make (optional but recommended)

## Quick Start

1. **Initial Setup**
   ```bash
   make setup-local
   ```
   This installs dependencies and creates configuration files.

2. **Configure Environment**
   Edit `.env.local` with your settings (the default values should work for most cases).

3. **Start Local Services**
   ```bash
   make start-local
   ```
   This starts LocalStack and the local API server.

4. **Access Local Services**
   - API Server: http://localhost:8000
   - LocalStack: http://localhost:4566
   - Health Check: http://localhost:8000/health

## Manual Setup (without Make)

1. **Install Dependencies**
   ```bash
   poetry install
   ```

2. **Copy Environment Configuration**
   ```bash
   cp .env.local.example .env.local
   ```

3. **Start LocalStack**
   ```bash
   docker-compose up -d localstack
   ```

4. **Initialize AWS Resources**
   ```bash
   docker-compose run --rm setup
   ```

5. **Start API Server**
   ```bash
   python run_local.py
   ```

## Testing with Local Environment

The local environment creates the following resources:

### DynamoDB Tables
- sensing-garden-detections
- sensing-garden-devices
- sensing-garden-classifications
- sensing-garden-models
- sensing-garden-videos

### S3 Buckets
- local-sensing-garden-images
- local-sensing-garden-videos

### Test Data
A test device (`test-device-001`) is automatically created for testing.

## API Testing Examples

```bash
# Health check
curl http://localhost:8000/health

# Get devices
curl http://localhost:8000/devices

# Get specific device
curl http://localhost:8000/devices/test-device-001

# Create a detection (example)
curl -X POST http://localhost:8000/detections \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-test-key" \
  -d '{
    "device_id": "test-device-001",
    "timestamp": "2024-01-01T12:00:00Z",
    "confidence": 0.95
  }'
```

## Environment Variables

Key environment variables in `.env.local`:

- `ENVIRONMENT=local` - Activates local configuration
- `AWS_ENDPOINT_URL` - LocalStack endpoint (default: http://localhost:4566)
- `S3_IMAGES_BUCKET` - Local images bucket name
- `S3_VIDEOS_BUCKET` - Local videos bucket name
- `SENSING_GARDEN_API_KEY` - API key for local testing

## Debugging

1. **View LocalStack Logs**
   ```bash
   docker-compose logs -f localstack
   ```

2. **Check AWS Resources**
   ```bash
   # List DynamoDB tables
   aws --endpoint-url=http://localhost:4566 dynamodb list-tables

   # List S3 buckets
   aws --endpoint-url=http://localhost:4566 s3 ls
   ```

3. **API Server Logs**
   The Flask development server shows request logs in the terminal.

## Cleanup

To stop all services and clean up:

```bash
make stop-local  # Stop services
make clean       # Remove all local data and containers
```

## Important Notes

- **Complete Isolation**: The local environment is completely isolated from production
- **Different Bucket Names**: Local S3 buckets use different names to prevent any conflicts
- **Test Credentials**: Uses hardcoded test credentials for LocalStack
- **No Production Access**: Cannot access production AWS resources from local environment

## Troubleshooting

1. **LocalStack won't start**: Ensure Docker is running and port 4566 is available
2. **Connection refused**: Wait a few seconds for LocalStack to fully initialize
3. **Module not found**: Ensure you're in the virtual environment with dependencies installed
4. **Permission denied**: Check Docker permissions or run with appropriate user

## Next Steps

Once your local environment is running, you can:
1. Implement new features and test locally
2. Run the test suite against local services
3. Debug Lambda functions with fast iteration
4. Test API changes without deployment