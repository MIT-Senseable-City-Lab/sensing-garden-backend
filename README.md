# Sensing Garden Backend

Backend services for the Sensing Garden project, including Lambda functions for image processing, DynamoDB for data storage, and S3 for image storage.

## Project Structure

- `lambda/`: Contains the Lambda function code
  - `src/`: Source code for Lambda functions
    - `handler.py`: Main Lambda handler functions
    - `dynamodb.py`: DynamoDB interaction functions
- `terraform/`: Infrastructure as Code using Terraform
- `dashboard/`: Web dashboard for viewing data
- `test_api.py`: Script for testing the API endpoints

## Setup

### Prerequisites

- Python 3.9+
- [Poetry](https://python-poetry.org/) for dependency management
- AWS account with appropriate permissions
- AWS CLI configured with your credentials

### Environment Variables

Set up API configuration using one of these methods:

1. **Environment Variables (Recommended for Production):**
   ```bash
   # Set these in your shell or .env file (don't commit .env to git)
   export SENSING_GARDEN_API_KEY="your-api-key"
   export API_BASE_URL="https://your-api-endpoint.execute-api.region.amazonaws.com"
   ```

2. **Using the Configuration Template:**
   ```bash
   # Copy the template to create your configuration
   cp api_config.template.py api_config.py
   
   # Then edit api_config.py with your credentials
   # Note: api_config.py is in .gitignore to prevent committing credentials
   ```

## Running the Dashboard

The dashboard provides a web interface to view data from your DynamoDB tables.

```bash
# Navigate to the dashboard directory
cd dashboard

# Install dependencies using Poetry
poetry install

# Run the dashboard
poetry run python app.py
```

The dashboard will be available at http://localhost:5050

## Testing the API

The test script allows you to test the detection and classification API endpoints.

```bash
# Install dependencies using Poetry (from the project root)
poetry install

# Run tests for both detection and classification
poetry run python test_api.py --test-type both

# Or run tests for just detection
poetry run python test_api.py --test-type detection

# Or run tests for just classification
poetry run python test_api.py --test-type classification
```

## Populating Sample Data

To populate the database with sample data for testing the dashboard:

```bash
cd dashboard
poetry run python populate_sample_data.py
```

## Deployment

### Backend Deployment

The backend services (Lambda, API Gateway, etc.) are deployed using Terraform:

```bash
cd terraform
terraform init
terraform apply
```

### Dashboard Deployment

The dashboard is deployed using AWS App Runner directly from GitHub for minimal maintenance. Just update the `repository_url` in `terraform/dashboard.tf` with your GitHub repository URL.

The dashboard will be automatically:
- Deployed when you push to the main branch
- SSL/TLS secured
- Auto-scaled based on traffic
- Monitored for container health

No manual build or push steps required! App Runner will handle the build and deployment process automatically.