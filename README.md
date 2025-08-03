# Sensing Garden Backend

Backend services for the Sensing Garden project, including Lambda functions for image processing and environmental data collection, DynamoDB for data storage, and S3 for image storage.

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
- AWS account with appropriate permissions
- AWS CLI configured with your credentials

### Environment Variables

Set up API configuration using environment variables:

```bash
# Set these in your shell or .env file (don't commit .env to git)
export SENSING_GARDEN_API_KEY="your-api-key"
export API_BASE_URL="https://your-api-endpoint.execute-api.region.amazonaws.com"
```




## API Endpoints

The backend provides the following REST API endpoints:

### Core Data Endpoints
- `GET /models` - Retrieve ML model information
- `POST /models` - Submit new model data
- `GET /detections` - Retrieve insect detection results with bounding boxes
- `POST /detections` - Submit new detection data
- `GET /classifications` - Retrieve insect species classification results
- `POST /classifications` - Submit new classification data
- `GET /videos` - Retrieve time-lapse videos of garden activity
- `POST /videos` - Upload new video data

### Environmental Data Endpoints
- `GET /environment` - Retrieve environmental sensor readings from garden monitoring devices
- `POST /environment` - Submit new environmental sensor data
- `GET /environment/count` - Get count of environmental readings

### Count Endpoints
- `GET /models/count` - Get count of models
- `GET /detections/count` - Get count of detections
- `GET /classifications/count` - Get count of classifications
- `GET /videos/count` - Get count of videos

### Environmental Data Format
Environmental readings include:
- **Particulate Matter**: PM1.0, PM2.5, PM4.0, PM10.0 concentrations (μg/m³)
- **Climate**: Ambient humidity (%) and temperature (°C)
- **Air Quality**: VOC (Volatile Organic Compounds) index and NOx (Nitrogen Oxides) index
- **Location**: GPS coordinates (latitude, longitude, optional altitude)

All endpoints support query parameters for filtering by device_id, time ranges, pagination, and sorting.

## Deployment

### Backend Deployment

The backend services (Lambda, API Gateway, etc.) are deployed using Terraform:

```bash
cd terraform
terraform init
terraform apply
```