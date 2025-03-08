import json
import os
from datetime import datetime
from decimal import Decimal
from functools import wraps

import boto3
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for


# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure AWS
aws_region = os.environ.get('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=aws_region)

# Table names
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'
MODELS_TABLE = 'models'

# Table mapping for routes
TABLE_MAPPING = {
    'detections': DETECTIONS_TABLE,
    'classifications': CLASSIFICATIONS_TABLE,
    'models': MODELS_TABLE
}

# Helper function to convert DynamoDB items to dict
def item_to_dict(item):
    if not item:
        return {}
    # Convert any non-serializable types
    for key, value in item.items():
        if isinstance(value, set):
            item[key] = list(value)
    return item

# Helper function to format timestamps in items
def format_timestamps(items):
    """Format timestamps for display in all items"""
    for item in items:
        if 'timestamp' in item:
            try:
                dt = datetime.fromisoformat(item['timestamp'])
                item['formatted_time'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                item['formatted_time'] = item['timestamp']
    return items

# Helper function to scan a DynamoDB table
def scan_table(table_name):
    """Generic function to scan a DynamoDB table"""
    table = dynamodb.Table(table_name)
    response = table.scan()
    items = response.get('Items', [])
    return format_timestamps(items)

@app.route('/')
def index():
    # Fetch all device IDs from the detections table
    table = dynamodb.Table(DETECTIONS_TABLE)
    response = table.scan(ProjectionExpression='device_id')
    device_ids = {item['device_id'] for item in response.get('Items', [])}
    return render_template('index.html', device_ids=device_ids)

@app.route('/view_device/<device_id>')
def view_device(device_id):
    # Fetch detection and classification content for the selected device
    detections = scan_table(DETECTIONS_TABLE)
    classifications = scan_table(CLASSIFICATIONS_TABLE)
    return render_template('device_content.html', 
                           device_id=device_id, 
                           detections=[d for d in detections if d['device_id'] == device_id], 
                           classifications=[c for c in classifications if c['device_id'] == device_id])

@app.route('/view_device/<device_id>/detections')
def view_device_detections(device_id):
    # Fetch detection content for the selected device
    detections = scan_table(DETECTIONS_TABLE)
    return render_template('device_detections.html', 
                           device_id=device_id, 
                           detections=[d for d in detections if d['device_id'] == device_id])

@app.route('/view_device/<device_id>/classifications')
def view_device_classifications(device_id):
    # Fetch classification content for the selected device
    classifications = scan_table(CLASSIFICATIONS_TABLE)
    return render_template('device_classifications.html', 
                           device_id=device_id, 
                           classifications=[c for c in classifications if c['device_id'] == device_id])

@app.route('/view_models')
def view_models():
    return view_table('models')

@app.route('/<table_type>')
def view_table(table_type):
    """Generic route handler for viewing any table"""
    if table_type not in TABLE_MAPPING:
        return redirect(url_for('index'))
    
    items = scan_table(TABLE_MAPPING[table_type])
    return render_template(f'{table_type}.html', items=items)

# For backward compatibility, keep the specific routes
@app.route('/models')
def models():
    return view_table('models')

@app.route('/item/<table_name>/<device_id>/<timestamp>')
def view_item(table_name, device_id, timestamp):
    table = dynamodb.Table(table_name)
    response = table.get_item(
        Key={
            'device_id': device_id,
            'timestamp': timestamp
        }
    )
    item = response.get('Item', {})
    
    return render_template('item_detail.html', 
                          item=item, 
                          table_name=table_name,
                          json_item=json.dumps(item_to_dict(item), indent=2))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5052)
