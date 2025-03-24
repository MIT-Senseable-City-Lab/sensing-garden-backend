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
    - `get_endpoints.py`: GET endpoint functions
    - `post_endpoints.py`: POST endpoint functions
    - `model_endpoints.py`: Model-related endpoint functions
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

The `sensing_garden_client` package provides functions to interact with the API endpoints.

```python
# Import the client and endpoint functions
from sensing_garden_client import SensingGardenClient
from sensing_garden_client import get_models, get_detections, get_classifications
from sensing_garden_client import send_detection_request, send_classification_request, send_model_request

# Create a client instance
client = SensingGardenClient(
    base_url="https://your-api-endpoint.execute-api.region.amazonaws.com",
    api_key="your-api-key"
)

# Use the endpoint functions
models = get_models(client, device_id="my-device")
detections = get_detections(client, device_id="my-device")
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