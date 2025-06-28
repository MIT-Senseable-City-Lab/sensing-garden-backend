#!/usr/bin/env python3
"""
Safety verification script to ensure local environment cannot access production.
Run this to verify your local setup is properly isolated.
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError

def check_production_access():
    """Verify that we cannot access production resources"""
    print("=== Local Environment Safety Check ===\n")
    
    # Check environment variable
    env = os.environ.get('ENVIRONMENT', 'not_set')
    endpoint = os.environ.get('AWS_ENDPOINT_URL', 'not_set')
    
    print(f"ENVIRONMENT: {env}")
    print(f"AWS_ENDPOINT_URL: {endpoint}")
    
    if env != 'local':
        print("\n⚠️  WARNING: ENVIRONMENT is not set to 'local'")
        return False
    
    if endpoint == 'not_set' or 'localhost' not in endpoint:
        print("\n⚠️  WARNING: AWS_ENDPOINT_URL is not pointing to localhost")
        return False
    
    print("\n✓ Environment variables correctly configured for local development")
    
    # Try to access production resources (this should fail)
    print("\nVerifying production isolation...")
    
    # Test 1: Try to list production S3 buckets
    try:
        s3_prod = boto3.client('s3')  # No endpoint_url = production
        buckets = s3_prod.list_buckets()
        if any('sensing-garden' in b['Name'] for b in buckets.get('Buckets', [])):
            print("\n❌ CRITICAL: Can access production S3 buckets!")
            print("Your local environment is NOT properly isolated!")
            return False
    except Exception as e:
        print("✓ Cannot access production S3 (this is good)")
    
    # Test 2: Try to access production DynamoDB
    try:
        ddb_prod = boto3.client('dynamodb', region_name='us-east-1')
        tables = ddb_prod.list_tables()
        if any('sensing-garden' in t for t in tables.get('TableNames', [])):
            print("\n❌ CRITICAL: Can access production DynamoDB tables!")
            print("Your local environment is NOT properly isolated!")
            return False
    except Exception as e:
        print("✓ Cannot access production DynamoDB (this is good)")
    
    # Test 3: Verify local services are accessible
    print("\nVerifying local services...")
    try:
        s3_local = boto3.client('s3', endpoint_url=endpoint)
        s3_local.list_buckets()
        print("✓ Can access local S3")
    except Exception as e:
        print(f"⚠️  Cannot access local S3: {e}")
        return False
    
    try:
        ddb_local = boto3.client('dynamodb', endpoint_url=endpoint)
        ddb_local.list_tables()
        print("✓ Can access local DynamoDB")
    except Exception as e:
        print(f"⚠️  Cannot access local DynamoDB: {e}")
        return False
    
    print("\n" + "="*50)
    print("✅ Local environment is properly isolated!")
    print("You can safely develop without risk to production.")
    print("="*50)
    return True

if __name__ == '__main__':
    # Load local environment
    from dotenv import load_dotenv
    load_dotenv('.env.local')
    
    if not check_production_access():
        print("\n⚠️  Safety check failed!")
        print("Please ensure your .env.local is properly configured.")
        sys.exit(1)
    
    sys.exit(0)