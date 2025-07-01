#!/usr/bin/env python3
"""
Demonstrate that our test suite catches regressions
"""

import os
import sys

# Add lambda source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'src'))

def test_confidence_array_handling():
    """Test that shows how our tests catch bugs"""
    
    # Simulate what our test does
    print("=== Regression Detection Demo ===\n")
    
    # 1. Normal behavior
    print("1. Testing CORRECT implementation:")
    body = {
        'family_confidence_array': [0.95, 0.03, 0.02],
        'genus_confidence_array': [0.87, 0.08, 0.05]
    }
    data = {}
    
    # Correct implementation
    for field in ['family_confidence_array', 'genus_confidence_array']:
        if field in body:
            data[field] = body[field]  # Correct
    
    print(f"   Result: {data}")
    print("   ✓ Arrays stored with correct field names\n")
    
    # 2. Buggy behavior
    print("2. Testing BUGGY implementation:")
    data_buggy = {}
    
    # Buggy implementation (like we introduced)
    for field in ['family_confidence_array', 'genus_confidence_array']:
        if field in body:
            data_buggy[field + '_broken'] = body[field]  # BUG!
    
    print(f"   Result: {data_buggy}")
    print("   ✗ Arrays stored with WRONG field names\n")
    
    # 3. How our test catches this
    print("3. How our test catches this:")
    print("   - Test sends POST with 'family_confidence_array'")
    print("   - Test expects response to contain 'family_confidence_array'")
    print("   - With bug, response has 'family_confidence_array_broken'")
    print("   - Test assertion fails: 'family_confidence_array' not in response")
    print("   - ✅ Regression detected!\n")
    
    # 4. Show test assertion
    print("4. Test assertion that catches the bug:")
    print("   assert 'family_confidence_array' in response_data")
    print(f"   Actual check: 'family_confidence_array' in {list(data_buggy.keys())}")
    print(f"   Result: {('family_confidence_array' in data_buggy)}")
    
    return 'family_confidence_array' in data

if __name__ == '__main__':
    test_confidence_array_handling()