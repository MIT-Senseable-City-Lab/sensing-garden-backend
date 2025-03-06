import os
import boto3
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from dotenv import load_dotenv
import json
from decimal import Decimal
from functools import wraps

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
def scan_table(table_name, limit=20):
    """Generic function to scan a DynamoDB table"""
    table = dynamodb.Table(table_name)
    response = table.scan(Limit=limit)
    items = response.get('Items', [])
    return format_timestamps(items)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/<table_type>')
def view_table(table_type):
    """Generic route handler for viewing any table"""
    if table_type not in TABLE_MAPPING:
        return redirect(url_for('index'))
    
    items = scan_table(TABLE_MAPPING[table_type])
    return render_template(f'{table_type}.html', items=items)

# For backward compatibility, keep the specific routes
@app.route('/detections')
def detections():
    return view_table('detections')

@app.route('/classifications')
def classifications():
    return view_table('classifications')

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
    app.run(debug=True, host='0.0.0.0', port=5050)
