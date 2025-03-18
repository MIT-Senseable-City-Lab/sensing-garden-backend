# Sensing Garden Dashboard

A simple web dashboard to view data from your DynamoDB tables for the Sensing Garden project.

## Setup Instructions

1. Install the required dependencies:

```bash
# Install Poetry if you don't have it already
# curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies using Poetry
poetry install
```

2. Configure API endpoint:

Set the API endpoint in your environment:
```bash
export API_BASE_URL=https://api.sensing-garden.com
```

3. (Optional) Populate sample data:

If you want to populate your DynamoDB tables with sample data for testing:

```bash
poetry run python populate_sample_data.py
```

4. Run the dashboard:

```bash
poetry run python app.py
```

5. Open your browser and navigate to:

```
http://localhost:5050
```

## Features

- View detection data including images and metadata
- View classification data including species information and confidence scores
- View model information
- View detailed information for each item
- Direct links to S3 images

## Tables Used

- `sensor_detections`: Stores detection data
- `sensor_classifications`: Stores classification data
- `models`: Stores model information

## Environment Variables

You can customize the dashboard by setting these environment variables:

- `API_BASE_URL`: Base URL for the API (default: 'https://api.sensing-garden.com')

## Notes

- This dashboard is for development and testing purposes only
- For production use, consider adding authentication and additional security measures
