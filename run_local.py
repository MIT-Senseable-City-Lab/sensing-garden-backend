#!/usr/bin/env python3
"""
Local development server for testing Lambda functions without deployment.
This simulates API Gateway routing to Lambda handlers.
"""

import os
import json
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load local environment variables
load_dotenv('.env.local')

# Add lambda source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'src'))

# Import the Lambda handler
from handler import lambda_handler

app = Flask(__name__)

def create_lambda_event(method, path, body=None, query_params=None, path_params=None):
    """Create a Lambda event object that mimics API Gateway"""
    event = {
        'httpMethod': method,
        'path': path,
        'pathParameters': path_params or {},
        'queryStringParameters': query_params or {},
        'headers': dict(request.headers),
        'body': json.dumps(body) if body else None,
        'isBase64Encoded': False
    }
    return event

def lambda_context():
    """Create a mock Lambda context"""
    class Context:
        function_name = 'local-lambda'
        function_version = '$LATEST'
        invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:local-lambda'
        memory_limit_in_mb = 256
        aws_request_id = 'local-request-id'
        log_group_name = '/aws/lambda/local-lambda'
        log_stream_name = 'local-stream'
        
        def get_remaining_time_in_millis(self):
            return 30000  # 30 seconds
    
    return Context()

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def handle_request(path):
    """Route all requests to the Lambda handler"""
    try:
        # Parse request body if present
        body = None
        if request.data:
            try:
                body = request.get_json()
            except:
                body = request.data.decode('utf-8')
        
        # Extract path parameters (simple pattern matching)
        path_params = {}
        if '{' in path and '}' in path:
            # This is a simplified path parameter extraction
            # In production, API Gateway does this more robustly
            parts = path.split('/')
            for i, part in enumerate(parts):
                if part.startswith('{') and part.endswith('}'):
                    param_name = part[1:-1]
                    if i < len(request.path.split('/')):
                        path_params[param_name] = request.path.split('/')[i]
        
        # Create Lambda event
        event = create_lambda_event(
            method=request.method,
            path=f"/{path}",
            body=body,
            query_params=dict(request.args),
            path_params=path_params
        )
        
        # Call Lambda handler
        response = lambda_handler(event, lambda_context())
        
        # Parse Lambda response
        status_code = response.get('statusCode', 200)
        headers = response.get('headers', {})
        body = response.get('body', '')
        
        # Try to parse body as JSON
        try:
            body = json.loads(body)
        except:
            pass
        
        # Return response
        resp = jsonify(body) if isinstance(body, (dict, list)) else body
        for key, value in headers.items():
            resp.headers[key] = value
        
        return resp, status_code
        
    except Exception as e:
        import traceback
        print(f"Error handling request: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'environment': 'local'})

if __name__ == '__main__':
    print("=== Sensing Garden Local API Server ===")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'local')}")
    print(f"LocalStack endpoint: {os.getenv('AWS_ENDPOINT_URL')}")
    print(f"S3 Images bucket: {os.getenv('S3_IMAGES_BUCKET')}")
    print(f"S3 Videos bucket: {os.getenv('S3_VIDEOS_BUCKET')}")
    print("\nStarting local API server on http://localhost:8000")
    print("Press Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=8000, debug=True)