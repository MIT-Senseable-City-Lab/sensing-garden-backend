import os
import boto3
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from dotenv import load_dotenv
import json
from decimal import Decimal

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

# Helper function to convert DynamoDB items to dict
def item_to_dict(item):
    if not item:
        return {}
    # Convert any non-serializable types
    for key, value in item.items():
        if isinstance(value, set):
            item[key] = list(value)
    return item

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/detections')
def detections():
    table = dynamodb.Table(DETECTIONS_TABLE)
    response = table.scan(Limit=20)
    items = response.get('Items', [])
    
    # Format timestamps for display
    for item in items:
        if 'timestamp' in item:
            try:
                dt = datetime.fromisoformat(item['timestamp'])
                item['formatted_time'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                item['formatted_time'] = item['timestamp']
    
    return render_template('detections.html', items=items)

@app.route('/classifications')
def classifications():
    table = dynamodb.Table(CLASSIFICATIONS_TABLE)
    response = table.scan(Limit=20)
    items = response.get('Items', [])
    
    # Format timestamps for display
    for item in items:
        if 'timestamp' in item:
            try:
                dt = datetime.fromisoformat(item['timestamp'])
                item['formatted_time'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                item['formatted_time'] = item['timestamp']
    
    return render_template('classifications.html', items=items)

@app.route('/models')
def models():
    table = dynamodb.Table(MODELS_TABLE)
    response = table.scan(Limit=20)
    items = response.get('Items', [])
    
    # Format timestamps for display
    for item in items:
        if 'timestamp' in item:
            try:
                dt = datetime.fromisoformat(item['timestamp'])
                item['formatted_time'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                item['formatted_time'] = item['timestamp']
    
    return render_template('models.html', items=items)

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
