import csv
import io
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv
from flask import (Flask, make_response, redirect, render_template, request,
                   url_for)

# Import all endpoints from get_endpoints
from get_endpoints import *

# Load environment variables
load_dotenv()

app = Flask(__name__)

def fetch_data(table_type: str, device_id: Optional[str] = None, next_token: Optional[str] = None) -> Dict[str, Any]:
    """Fetch data from the API for a specific table type with pagination support"""
    # Hardcoded limit of 50 items per page
    limit: int = 50
    try:
        if table_type == 'detections':
            response = get_detections(device_id=device_id, limit=limit, next_token=next_token)
        elif table_type == 'classifications':
            response = get_classifications(device_id=device_id, limit=limit, next_token=next_token)
        elif table_type == 'models':
            response = get_models(limit=limit, next_token=next_token)
        else:
            return {'items': [], 'next_token': None}
        
        # Extract the list of items and next_token from the response
        items = response.get('items', [])
        next_token = response.get('next_token', None)
        
        # Add formatted timestamp to each item
        for item in items:
            if 'timestamp' in item:
                try:
                    # Assuming ISO 8601 format
                    timestamp = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                    # Format timestamp for display
                    item['formatted_time'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError) as e:
                    print(f"Error formatting timestamp {item.get('timestamp')}: {str(e)}")
                    item['formatted_time'] = item.get('timestamp', '')
        
        return {'items': items, 'next_token': next_token}
    except Exception as e:
        print(f"Error fetching {table_type} data: {str(e)}")
        return {'items': [], 'next_token': None}

def get_field_names(items: List[Dict]) -> List[str]:
    """Extract field names from the first item in a list"""
    if not items:
        return []
    # Get all keys from the first item
    return list(items[0].keys()) if items else []

@app.route('/')
def index():
    # Fetch all device IDs from the detections data
    result = fetch_data('detections')  # Using hardcoded limit of 50 items per page
    device_ids = {item['device_id'] for item in result['items'] if 'device_id' in item}
    return render_template('index.html', device_ids=device_ids)

@app.route('/view_device/<device_id>')
def view_device(device_id):
    # Fetch detection and classification content for the selected device
    detection_result = fetch_data('detections', device_id=device_id)
    classification_result = fetch_data('classifications', device_id=device_id)
    
    # Get field names directly from the data
    detection_fields = get_field_names(detection_result['items'])
    classification_fields = get_field_names(classification_result['items'])
    
    return render_template('device_content.html', 
                           device_id=device_id, 
                           detections=detection_result['items'],
                           classifications=classification_result['items'],
                           detection_fields=detection_fields,
                           classification_fields=classification_fields)

@app.route('/view_device/<device_id>/detections')
def view_device_detections(device_id):
    # Get pagination token from request if available
    next_token = request.args.get('next_token', None)
    prev_token = request.args.get('prev_token', None)
    
    # Track page tokens for Previous button
    token_history = request.args.get('token_history', '')
    current_page = int(request.args.get('page', '1'))
    
    # Process token history
    token_list = token_history.split(',') if token_history else []
    
    # Fetch detection content for the selected device with pagination
    result = fetch_data('detections', device_id=device_id, next_token=next_token)
    print(f"Fetched detections for device {device_id}, next_token: {next_token}, page: {current_page}")
    
    # Get field names directly from the data
    fields = get_field_names(result['items'])
    if 'formatted_time' not in fields and 'timestamp' in fields:
        fields.append('formatted_time')  # Add formatted_time for display purposes
    
    # Update token history if moving forward
    if next_token and next_token not in token_list:
        if current_page > len(token_list):
            token_list.append(next_token)
    
    # Get previous token (if we're not on the first page)
    prev_url = None
    if current_page > 1:
        if current_page == 2:  # Going back to first page
            prev_url = url_for('view_device_detections', device_id=device_id, page=1)
        else:  # Going back to previous page
            prev_token = token_list[current_page-3] if current_page > 2 and len(token_list) >= current_page-2 else None
            prev_url = url_for('view_device_detections', 
                              device_id=device_id, 
                              next_token=prev_token,
                              token_history=','.join(token_list[:current_page-2]),
                              page=current_page-1)
    
    # Generate pagination URLs
    next_page_token = result['next_token']
    pagination = {
        'has_next': next_page_token is not None,
        'next_url': url_for('view_device_detections', 
                           device_id=device_id, 
                           next_token=next_page_token,
                           token_history=','.join(token_list),
                           page=current_page+1) if next_page_token else None,
        'has_prev': current_page > 1,
        'prev_url': prev_url
    }
    
    return render_template('device_detections.html', 
                           device_id=device_id, 
                           detections=result['items'],
                           fields=fields,
                           pagination=pagination)

@app.route('/view_device/<device_id>/classifications')
def view_device_classifications(device_id):
    # Get pagination token from request if available
    next_token = request.args.get('next_token', None)
    prev_token = request.args.get('prev_token', None)
    
    # Track page tokens for Previous button
    token_history = request.args.get('token_history', '')
    current_page = int(request.args.get('page', '1'))
    
    # Process token history
    token_list = token_history.split(',') if token_history else []
    
    # Fetch classification content for the selected device with pagination
    result = fetch_data('classifications', device_id=device_id, next_token=next_token)
    print(f"Fetched classifications for device {device_id}, next_token: {next_token}, page: {current_page}")
    
    # Get field names directly from the data
    fields = get_field_names(result['items'])
    if 'formatted_time' not in fields and 'timestamp' in fields:
        fields.append('formatted_time')  # Add formatted_time for display purposes
    
    # Update token history if moving forward
    if next_token and next_token not in token_list:
        if current_page > len(token_list):
            token_list.append(next_token)
    
    # Get previous token (if we're not on the first page)
    prev_url = None
    if current_page > 1:
        if current_page == 2:  # Going back to first page
            prev_url = url_for('view_device_classifications', device_id=device_id, page=1)
        else:  # Going back to previous page
            prev_token = token_list[current_page-3] if current_page > 2 and len(token_list) >= current_page-2 else None
            prev_url = url_for('view_device_classifications', 
                              device_id=device_id, 
                              next_token=prev_token,
                              token_history=','.join(token_list[:current_page-2]),
                              page=current_page-1)
    
    # Generate pagination URLs
    next_page_token = result['next_token']
    pagination = {
        'has_next': next_page_token is not None,
        'next_url': url_for('view_device_classifications', 
                           device_id=device_id, 
                           next_token=next_page_token,
                           token_history=','.join(token_list),
                           page=current_page+1) if next_page_token else None,
        'has_prev': current_page > 1,
        'prev_url': prev_url
    }
    
    return render_template('device_classifications.html', 
                           device_id=device_id, 
                           classifications=result['items'],
                           fields=fields,
                           pagination=pagination)

@app.route('/view_models')
def view_models():
    # Get pagination token from request if available
    next_token = request.args.get('next_token', None)
    prev_token = request.args.get('prev_token', None)
    
    # Track page tokens for Previous button
    token_history = request.args.get('token_history', '')
    current_page = int(request.args.get('page', '1'))
    
    # Process token history
    token_list = token_history.split(',') if token_history else []
    
    # Directly fetch models data with pagination
    result = fetch_data('models', next_token=next_token)
    fields = get_field_names(result['items'])
    
    # Handle special case for models - map 'id' to 'model_id' for backwards compatibility
    for item in result['items']:
        if 'id' in item and 'model_id' not in item:
            item['model_id'] = item['id']
            
    # Update token history if moving forward
    if next_token and next_token not in token_list:
        if current_page > len(token_list):
            token_list.append(next_token)
    
    # Get previous token (if we're not on the first page)
    prev_url = None
    if current_page > 1:
        if current_page == 2:  # Going back to first page
            prev_url = url_for('view_models', page=1)
        else:  # Going back to previous page
            prev_token = token_list[current_page-3] if current_page > 2 and len(token_list) >= current_page-2 else None
            prev_url = url_for('view_models', 
                              next_token=prev_token,
                              token_history=','.join(token_list[:current_page-2]),
                              page=current_page-1)
    
    # Generate pagination URLs
    next_page_token = result['next_token']
    pagination = {
        'has_next': next_page_token is not None,
        'next_url': url_for('view_models', 
                           next_token=next_page_token,
                           token_history=','.join(token_list),
                           page=current_page+1) if next_page_token else None,
        'has_prev': current_page > 1,
        'prev_url': prev_url
    }
    
    return render_template('models.html', 
                          items=result['items'], 
                          fields=fields,
                          pagination=pagination)

@app.route('/<table_type>')
def view_table(table_type):
    """Generic route handler for viewing any table with pagination"""
    # Only allow known table types
    if table_type not in ['detections', 'classifications', 'models']:
        return redirect(url_for('index'))
    
    # Get pagination token from request if available
    next_token = request.args.get('next_token', None)
    prev_token = request.args.get('prev_token', None)
    
    # Track page tokens for Previous button
    token_history = request.args.get('token_history', '')
    current_page = int(request.args.get('page', '1'))
    
    # Process token history
    token_list = token_history.split(',') if token_history else []
    
    # Fetch data with pagination
    result = fetch_data(table_type, next_token=next_token)
    fields = get_field_names(result['items'])
    
    # Handle special case for models - map 'id' to 'model_id' for backwards compatibility
    if table_type == 'models':
        for item in result['items']:
            if 'id' in item and 'model_id' not in item:
                item['model_id'] = item['id']
                
    # Update token history if moving forward
    if next_token and next_token not in token_list:
        if current_page > len(token_list):
            token_list.append(next_token)
    
    # Get previous token (if we're not on the first page)
    prev_url = None
    if current_page > 1:
        if current_page == 2:  # Going back to first page
            prev_url = url_for('view_table', table_type=table_type, page=1)
        else:  # Going back to previous page
            prev_token = token_list[current_page-3] if current_page > 2 and len(token_list) >= current_page-2 else None
            prev_url = url_for('view_table', 
                              table_type=table_type,
                              next_token=prev_token,
                              token_history=','.join(token_list[:current_page-2]),
                              page=current_page-1)
    
    # Generate pagination URLs
    next_page_token = result['next_token']
    pagination = {
        'has_next': next_page_token is not None,
        'next_url': url_for('view_table', 
                           table_type=table_type,
                           next_token=next_page_token,
                           token_history=','.join(token_list),
                           page=current_page+1) if next_page_token else None,
        'has_prev': current_page > 1,
        'prev_url': prev_url
    }
    
    return render_template(f'{table_type}.html', 
                          items=result['items'], 
                          fields=fields,
                          pagination=pagination)

# For backward compatibility, keep the specific routes
@app.route('/models')
def models():
    return view_models()

@app.route('/item/<table_type>/<device_id>/<timestamp>')
def view_item(table_type, device_id, timestamp):
    # Try to fetch the individual item
    if table_type == 'models':
        item = get_model(device_id)
    elif table_type == 'detections':
        item = get_detection(device_id, timestamp)
    elif table_type == 'classifications':
        item = get_classification(device_id, timestamp)
    else:
        return "Invalid table type", 404
    
    # Get field names directly from the item
    fields = list(item.keys()) if item else []
    
    return render_template('item_detail.html', 
                          item=item, 
                          table_name=table_type,
                          fields=fields,
                          json_item=json.dumps(item, indent=2))

@app.route('/download_csv/<table_type>', defaults={'device_id': None})
@app.route('/download_csv/<table_type>/<device_id>')
def download_csv(table_type, device_id):
    """Download table data as CSV"""
    if table_type not in ['detections', 'classifications', 'models']:
        return redirect(url_for('index'))

    result = fetch_data(table_type, device_id=device_id)
    items = result['items']

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
    file_name = f"{table_type}_{device_id}_{datetime.now().isoformat()}.csv" if device_id else f"{table_type}_{datetime.now().isoformat()}.csv"
    response.headers['Content-Disposition'] = f'attachment; filename={file_name}'
    response.headers['Content-Type'] = 'text/csv'
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5052)
