import csv
import io
import json
import os
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv
from flask import (Flask, make_response, redirect, render_template, request,
                   url_for)


# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure API endpoint
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://api.sensing-garden.com')

# Load database schema
root_dir = Path(__file__).parent.parent
schema_path = root_dir / 'common' / 'db-schema.json'

def load_schema(schema_path):
    """Load the database schema with proper error handling"""
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            print(f"Schema loaded successfully from {schema_path}")
            return schema
    except FileNotFoundError:
        error_msg = f"Database schema file not found at {schema_path}"
        print(error_msg)
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in schema file {schema_path}: {str(e)}"
        print(error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Failed to load schema from {schema_path}: {str(e)}"
        print(error_msg)
        sys.exit(1)

# Load the schema
SCHEMA = load_schema(schema_path)

# Table names
DETECTIONS_TABLE = 'detections'
CLASSIFICATIONS_TABLE = 'classifications'
MODELS_TABLE = 'models'

# Table mapping for routes
TABLE_MAPPING = {
    'detections': DETECTIONS_TABLE,
    'classifications': CLASSIFICATIONS_TABLE,
    'models': MODELS_TABLE
}

# Get field names from schema
def get_table_fields(table_name):
    """Get required fields for a table from schema"""
    if table_name in SCHEMA['properties']:
        return SCHEMA['properties'][table_name]['required']
    return []

def get_table_properties(table_name):
    """Get property definitions for a table from schema"""
    if table_name in SCHEMA['properties']:
        return SCHEMA['properties'][table_name]['properties']
    return {}

def fetch_data(table_type: str, device_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """Fetch data from the API for a specific table type"""
    try:
        params = {
            'limit': limit
        }
        if device_id:
            params['device_id'] = device_id
            
        response = requests.get(
            f"{API_BASE_URL}/{table_type}",
            params=params
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get('items', [])
    except Exception as e:
        print(f"Error fetching {table_type} data: {str(e)}")
        return []

@app.route('/')
def index():
    # Fetch all device IDs from the detections data
    detections = fetch_data('detections')
    device_ids = {item['device_id'] for item in detections}
    return render_template('index.html', device_ids=device_ids)

@app.route('/view_device/<device_id>')
def view_device(device_id):
    # Fetch detection and classification content for the selected device
    detections = fetch_data('detections', device_id=device_id)
    classifications = fetch_data('classifications', device_id=device_id)
    
    # Get field names from schema
    detection_fields = get_table_fields(DETECTIONS_TABLE)
    classification_fields = get_table_fields(CLASSIFICATIONS_TABLE)
    
    return render_template('device_content.html', 
                           device_id=device_id, 
                           detections=detections,
                           classifications=classifications,
                           detection_fields=detection_fields,
                           classification_fields=classification_fields)

@app.route('/view_device/<device_id>/detections')
def view_device_detections(device_id):
    # Fetch detection content for the selected device
    detections = fetch_data('detections', device_id=device_id)
    
    # Get field names from schema
    detection_fields = get_table_fields(DETECTIONS_TABLE)
    
    return render_template('device_detections.html', 
                           device_id=device_id, 
                           detections=detections,
                           fields=detection_fields)

@app.route('/view_device/<device_id>/classifications')
def view_device_classifications(device_id):
    # Fetch classification content for the selected device
    classifications = fetch_data('classifications', device_id=device_id)
    
    # Get field names from schema
    classification_fields = get_table_fields(CLASSIFICATIONS_TABLE)
    
    return render_template('device_classifications.html', 
                           device_id=device_id, 
                           classifications=classifications,
                           fields=classification_fields)

@app.route('/view_models')
def view_models():
    return view_table('models')

@app.route('/<table_type>')
def view_table(table_type):
    """Generic route handler for viewing any table"""
    if table_type not in TABLE_MAPPING:
        return redirect(url_for('index'))
    
    table_name = TABLE_MAPPING[table_type]
    items = scan_table(table_name)
    
    # Get field names from schema
    fields = get_table_fields(table_name)
    
    # Handle special case for models table - map 'id' to 'model_id' for backwards compatibility
    if table_name == MODELS_TABLE:
        for item in items:
            if 'id' in item and 'model_id' not in item:
                item['model_id'] = item['id']
    
    return render_template(f'{table_type}.html', 
                          items=items, 
                          fields=fields,
                          table_properties=get_table_properties(table_name))

# For backward compatibility, keep the specific routes
@app.route('/models')
def models():
    return view_table('models')

@app.route('/item/<table_name>/<device_id>/<timestamp>')
def view_item(table_name, device_id, timestamp):
    table = dynamodb.Table(table_name)
    
    # Define the key fields based on the table
    key_fields = {'device_id': device_id, 'timestamp': timestamp}
    
    # For models table, use 'id' instead of 'device_id'
    if table_name == MODELS_TABLE:
        key_fields = {'id': device_id, 'timestamp': timestamp}
    
    response = table.get_item(Key=key_fields)
    item = response.get('Item', {})
    
    # Get field names from schema for this table
    fields = get_table_fields(table_name) if table_name in SCHEMA['properties']['db']['properties'] else []
    
    return render_template('item_detail.html', 
                          item=item, 
                          table_name=table_name,
                          fields=fields,
                          json_item=json.dumps(item_to_dict(item), indent=2))

@app.route('/download_csv/<table_name>', defaults={'device_id': None})
@app.route('/download_csv/<table_name>/<device_id>')
def download_csv(table_name, device_id):
    """Download table data as CSV"""
    if table_name not in TABLE_MAPPING:
        return redirect(url_for('index'))

    items = scan_table(TABLE_MAPPING[table_name])
    if device_id:
        items = [item for item in items if item.get('device_id') == device_id]

    if not items:
        return "No data available", 404

    # Get all possible fieldnames
    fieldnames = set()
    for item in items:
        fieldnames.update(item.keys())
    fieldnames = sorted(fieldnames)

    csv_data = io.StringIO()
    writer = csv.DictWriter(csv_data, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for item in items:
        # Flatten nested structures
        flat_item = {}
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                flat_item[key] = json.dumps(value)
            else:
                flat_item[key] = value
        writer.writerow(flat_item)

    response = make_response(csv_data.getvalue())
    file_name = f"{table_name}_{device_id}_{datetime.now().isoformat()}.csv" if device_id else f"{table_name}_{datetime.now().isoformat()}.csv"
    response.headers['Content-Disposition'] = f'attachment; filename={file_name}'
    response.headers['Content-Type'] = 'text/csv'
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5052)
