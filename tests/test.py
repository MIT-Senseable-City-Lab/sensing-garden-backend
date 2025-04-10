#!/usr/bin/env python3
"""
Master test runner for the Sensing Garden API.
This script runs all test files or specific test categories as specified.
"""
import argparse
import importlib
import os
import sys
import unittest
from typing import List, Optional

# Test modules to run
TEST_MODULES = {
    "videos": "test_videos",
    "detections": "test_detections",
    "classifications": "test_classifications",
    "models": "test_models"
}

def run_test_module(module_name: str) -> bool:
    """
    Run a specific test module as a standalone script.
    
    Args:
        module_name: Name of the module to run
        
    Returns:
        bool: Whether the test was successful
    """
    print(f"\n{'='*80}")
    print(f"Running {module_name} tests...")
    print(f"{'='*80}\n")
    
    # Import the module
    try:
        # Run the module as a script
        module_path = os.path.join(os.path.dirname(__file__), f"{module_name}.py")
        result = os.system(f"python {module_path}")
        success = result == 0
        
        if success:
            print(f"\n✅ {module_name} tests passed!")
        else:
            print(f"\n❌ {module_name} tests failed!")
        
        return success
    except Exception as e:
        print(f"Error running {module_name}: {str(e)}")
        return False

def run_tests(test_types: Optional[List[str]] = None) -> bool:
    """
    Run all tests or specific test types.
    
    Args:
        test_types: List of test types to run, or None to run all
        
    Returns:
        bool: Whether all tests passed
    """
    # If no test types specified, run all
    if not test_types:
        test_types = list(TEST_MODULES.keys())
    
    # Track overall success
    all_success = True
    
    # Run each test type
    for test_type in test_types:
        if test_type in TEST_MODULES:
            module_name = TEST_MODULES[test_type]
            success = run_test_module(module_name)
            all_success = all_success and success
        else:
            print(f"Unknown test type: {test_type}")
            all_success = False
    
    # Print overall results
    print(f"\n{'='*80}")
    if all_success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    print(f"{'='*80}\n")
    
    return all_success

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run Sensing Garden API tests')
    parser.add_argument('test_types', nargs='*', choices=list(TEST_MODULES.keys()) + ['all'],
                        help='Test types to run (default: all)')
    
    args = parser.parse_args()
    
    # Determine which tests to run
    test_types = None  # Run all by default
    if args.test_types and 'all' not in args.test_types:
        test_types = args.test_types
    
    # Run the tests
    success = run_tests(test_types)
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
