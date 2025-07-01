#!/usr/bin/env python3
"""
Script to test that our test suite catches regressions.
This will temporarily break the Lambda handler and run tests to show failures.
"""

import subprocess
import os
import sys
import shutil

def run_test_and_capture_output():
    """Run a specific test and capture output"""
    # Set environment variables
    env = os.environ.copy()
    env.update({
        'ENVIRONMENT': 'local',
        'AWS_ENDPOINT_URL': 'http://localhost:4566',
        'AWS_ACCESS_KEY_ID': 'test',
        'AWS_SECRET_ACCESS_KEY': 'test'
    })
    
    # Run a specific test that should fail
    cmd = [
        'python', '-m', 'pytest', 
        'tests/test_handler.py::TestClassificationEndpoints::test_post_classification_with_arrays',
        '-v', '--tb=short'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr

def main():
    print("=== Testing Regression Detection ===\n")
    
    # First, backup the original handler
    handler_path = 'lambda/src/handler.py'
    backup_path = 'lambda/src/handler.py.backup'
    
    print("1. Creating backup of handler.py...")
    shutil.copy2(handler_path, backup_path)
    
    try:
        # Break the handler by introducing a bug in confidence array handling
        print("2. Introducing a bug in confidence array handling...")
        
        with open(handler_path, 'r') as f:
            content = f.read()
        
        # Break the confidence array handling by changing the field name
        broken_content = content.replace(
            "data[field] = [Decimal(str(x)) for x in body[field]]",
            "data[field + '_broken'] = [Decimal(str(x)) for x in body[field]]  # BUG: Wrong field name"
        )
        
        with open(handler_path, 'w') as f:
            f.write(broken_content)
        
        print("   Bug introduced: confidence arrays will be stored with wrong field names")
        
        # Run the test
        print("\n3. Running test that should FAIL...")
        print("-" * 60)
        
        returncode, stdout, stderr = run_test_and_capture_output()
        
        print(stdout)
        if stderr:
            print("STDERR:", stderr)
        
        print("-" * 60)
        
        if returncode != 0:
            print("\n✅ SUCCESS: Test correctly detected the regression!")
            print("   The test failed as expected when we broke the code.")
        else:
            print("\n❌ PROBLEM: Test passed even with broken code!")
            print("   This suggests the test isn't comprehensive enough.")
        
        # Show what the test was checking
        print("\n4. What the test was checking:")
        print("   - POST to /classifications with confidence arrays")
        print("   - Verify the arrays are stored correctly")
        print("   - The bug made arrays store as 'field_broken' instead of 'field'")
        print("   - The test caught this because it checks the response data")
        
    finally:
        # Restore the original handler
        print("\n5. Restoring original handler.py...")
        shutil.move(backup_path, handler_path)
        print("   ✓ Original code restored")
    
    print("\n=== Regression Detection Test Complete ===")
    
    if returncode != 0:
        print("\nThe test suite successfully detects regressions! 🎉")
        print("When code is broken, tests fail as expected.")
        return 0
    else:
        return 1

if __name__ == '__main__':
    sys.exit(main())