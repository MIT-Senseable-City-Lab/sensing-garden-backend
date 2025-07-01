# Sensing Garden Backend

Backend services for the Sensing Garden project, including Lambda functions for image processing, DynamoDB for data storage, and S3 for image storage.

⚠️ **Note:** The Python client (`sensing_garden_client`) and its accompanying tests have been moved to the separate [`sensing-garden-client`](https://github.com/daydemir/sensing-garden-client) repository. This backend repository now contains only infrastructure and AWS-related code.

## Project Structure

- `lambda/`: Contains the Lambda function code
  - `src/`: Source code for Lambda functions
    - `handler.py`: Main Lambda handler functions
    - `dynamodb.py`: DynamoDB interaction functions
- `terraform/`: Infrastructure as Code using Terraform

## Setup

### Prerequisites

- Python 3.9+
- [Poetry](https://python-poetry.org/) for dependency management
- AWS account with appropriate permissions (for production deployment)
- AWS CLI configured with your credentials (for production deployment)
- Docker and Docker Compose (for local development)

### Local Development

For local development and testing, see [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md). The local setup provides a complete isolated environment using LocalStack that simulates AWS services without touching production resources.

### Environment Variables

Set up API configuration using environment variables:

```bash
# Set these in your shell or .env file (don't commit .env to git)
export SENSING_GARDEN_API_KEY="your-api-key"
export API_BASE_URL="https://your-api-endpoint.execute-api.region.amazonaws.com"
```




## API Changes

### Classification Confidence Arrays (v2)

The classifications API now supports optional array fields for storing full probability distributions:

- `family_confidence_array`: Array of confidence scores for all possible families
- `genus_confidence_array`: Array of confidence scores for all possible genera  
- `species_confidence_array`: Array of confidence scores for all possible species

These fields are optional and backward compatible. Existing clients continue to work without modification.

## Deployment

### Backend Deployment

The backend services (Lambda, API Gateway, etc.) are deployed using Terraform:

```bash
cd terraform
terraform init
terraform apply
```