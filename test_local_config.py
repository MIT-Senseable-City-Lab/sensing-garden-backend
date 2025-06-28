#!/usr/bin/env python3
"""
Test that the configuration is properly set up for local development
"""

import os
import sys

# Set environment for local testing
os.environ['ENVIRONMENT'] = 'local'
os.environ['AWS_ENDPOINT_URL'] = 'http://localhost:4566'

# Add lambda source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'src'))

import config

def test_config():
    """Test configuration is set correctly"""
    cfg = config.get_config()
    
    print("Testing local configuration...")
    print(f"Environment: {cfg['environment']}")
    print(f"AWS Endpoint: {cfg['aws_endpoint_url']}")
    print(f"Images Bucket: {cfg['images_bucket']}")
    print(f"Videos Bucket: {cfg['videos_bucket']}")
    
    assert cfg['environment'] == 'local', "Environment should be 'local'"
    assert cfg['aws_endpoint_url'] == 'http://localhost:4566', "Should use LocalStack endpoint"
    assert cfg['images_bucket'] == 'local-sensing-garden-images', "Should use local images bucket"
    assert cfg['videos_bucket'] == 'local-sensing-garden-videos', "Should use local videos bucket"
    
    print("\n✓ All configuration checks passed!")

if __name__ == '__main__':
    test_config()