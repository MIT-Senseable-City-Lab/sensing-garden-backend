# Sensing Garden Backend

Backend services for the Sensing Garden project, including Lambda functions for image processing, DynamoDB for data storage, and S3 for image storage.

## Project Structure

- `lambda/`: Contains the Lambda function code
  - `src/`: Source code for Lambda functions
    - `handler.py`: Main Lambda handler functions
    - `dynamodb.py`: DynamoDB interaction functions
- `terraform/`: Infrastructure as Code using Terraform
- `sensing_garden_client/`: Python package for API interaction
  - `sensing_garden_client/`: Source code for the API client and endpoints
    - `client.py`: Core client for interacting with the API
    - `videos.py`: Video upload and retrieval client
    - `models.py`, `detections.py`, `classifications.py`: Domain-specific clients
    - (Legacy endpoint function files have been removed; use the new client API)
- `test_get_api.py`: Script for testing the GET API endpoints
- `test_post_api.py`: Script for testing the POST API endpoints

## Setup

### Prerequisites

- Python 3.9+
- [Poetry](https://python-poetry.org/) for dependency management
- AWS account with appropriate permissions
- AWS CLI configured with your credentials

### Environment Variables

Set up API configuration using environment variables:

```bash
# Set these in your shell or .env file (don't commit .env to git)
export SENSING_GARDEN_API_KEY="your-api-key"
export API_BASE_URL="https://your-api-endpoint.execute-api.region.amazonaws.com"
```

## Using the Sensing Garden Client Package

The `sensing_garden_client` package is now available on PyPI and provides a modern, object-oriented client for all API operations. **As of v0.0.7, all tests and examples use the real client logic and the new constructor-based initialization.**

**New in v0.0.12:**
- Added support for optional `track_id` and `metadata` fields in classifications (and backend).
- All tests updated and passing for these features.

Install from PyPI:

```bash
pip install sensing_garden_client
```

Or use Poetry (recommended for development):

```bash
poetry add sensing_garden_client
```

### Example Usage

```python
from sensing_garden_client import SensingGardenClient

client = SensingGardenClient(
    base_url="https://your-api-endpoint.execute-api.region.amazonaws.com",
    api_key="your-api-key",
    aws_access_key_id="your-aws-access-key-id",         # Required for video upload
    aws_secret_access_key="your-aws-secret-access-key"  # Required for video upload
)

# Upload a video
with open("my_video.mp4", "rb") as f:
    video_data = f.read()

result = client.videos.upload_video(
    device_id="my-device",
    timestamp="2025-04-15T18:53:46-04:00",
    video_path_or_data=video_data,
    content_type="video/mp4"
)
print(result)

# Add a classification with bounding box, track_id, and metadata
classification = client.classifications.add(
    device_id="device-123",
    model_id="model-456",
    image_data=image_data,
    family="Rosaceae",
    genus="Rosa",
    species="Rosa gallica",
    family_confidence=0.95,
    genus_confidence=0.92,
    species_confidence=0.89,
    timestamp="2023-06-01T12:34:56Z",
    bounding_box=[0.1, 0.2, 0.3, 0.4],
    track_id="track-abc123",            # Optional tracking ID
    metadata={"source": "drone", "weather": "sunny"}  # Optional metadata dict
)
print(classification)
```

**Note:** The video upload API no longer requires or accepts a `description` field. Only `device_id`, `timestamp`, `video_key`, and optional `metadata` are supported.

### Testing and Development
- All tests use the real `sensing_garden_client` logic (no mocks/stubs).
- Robust GET tests: All created models and videos are verified by fetching all items and checking for presence, not by strict filtering.
- Legacy endpoint files (`get_endpoints.py`, `post_endpoints.py`, etc.) have been removed. Use the client API for all operations.
- For local testing, use `poetry run pytest tests` in the project root.
- The client package is versioned and published to PyPI; always use the latest version for new projects.

### Troubleshooting
If you see errors like `ModuleNotFoundError: No module named 'botocore.vendored.six.moves'`, ensure you are running tests and scripts inside your Poetry-managed environment, and update boto3/botocore using:

```sh
poetry update boto3 botocore
```

For development, install the package in development mode:

```bash
# From the project root
cd sensing_garden_client
poetry install
```

## Testing the API

There are separate test scripts for GET and POST API endpoints.

```bash
# Install dependencies using Poetry (from the project root)
poetry install

# Run tests for GET endpoints
poetry run python test_get_api.py

# Run tests for POST endpoints
poetry run python test_post_api.py

# Run tests with specific parameters
poetry run python test_get_api.py --device my-device --model-id my-model
```

## Populating Sample Data

To populate the database with sample data for testing:

```bash
# Add test data for a specific device and model
poetry run python test_post_api.py --add-test-data --device-id my-device --model-id my-model
```

## Deployment

### Backend Deployment

The backend services (Lambda, API Gateway, etc.) are deployed using Terraform:

```bash
cd terraform
terraform init
terraform apply
```

### API Package Deployment

The `sensing_garden_client` package can be installed directly from the repository or published to PyPI for easier consumption:

```bash
# Install from GitHub
pip install git+https://github.com/your-username/sensing-garden-backend.git#subdirectory=sensing_garden_client

# Or if published to PyPI
pip install sensing_garden_client
```