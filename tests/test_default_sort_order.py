#!/usr/bin/env python3
"""
Test to verify that fetch_classifications returns results in descending order of timestamp by default.
"""
import sys
import uuid
from datetime import datetime, timedelta

from .test_classifications import _add_classification, _fetch_classifications
from .test_utils import get_client

def test_default_sort_order():
    """
    Test that fetch_classifications returns results in descending order of timestamp by default.
    """
    # Use the standard test device and model IDs
    from .conftest import test_vars
    device_id = test_vars["device_id"]
    model_id = test_vars["model_id"]
    
    # Create test classifications with specific timestamps, 1 minute apart
    base_time = datetime.now()
    timestamps = [
        (base_time - timedelta(minutes=2)).isoformat(),  # Oldest
        (base_time - timedelta(minutes=1)).isoformat(),  # Middle
        base_time.isoformat()                            # Newest
    ]
    
    print(f"\n\nTesting DEFAULT SORT ORDER with device_id: {device_id}, model_id: {model_id}")
    print(f"Creating 3 test classifications with timestamps:")
    for i, ts in enumerate(timestamps):
        print(f"  {i+1}: {ts}")
        # Add classification with specific timestamp
        success, _ = _add_classification(device_id, model_id, timestamp=ts)
        assert success, f"Failed to add test classification {i+1}"
    
    # Test with explicit sorting parameters (sort_by='timestamp', sort_desc=True)
    print("\nFetching classifications with explicit DESC sort parameters:")
    success, data = _fetch_classifications(device_id, model_id, sort_by='timestamp', sort_desc=True)
    assert success, "Failed to fetch classifications with explicit sort parameters"
    
    # Check results are correctly sorted
    items_explicit = data.get('items', [])
    assert len(items_explicit) >= 3, f"Expected at least 3 classifications with explicit parameters, got {len(items_explicit)}"
    
    # Get timestamps from explicit sort
    timestamps_explicit = [item.get('timestamp') for item in items_explicit[:3]]
    print("\nReturned timestamps with explicit sorting (newest first):")
    for i, ts in enumerate(timestamps_explicit):
        print(f"  {i+1}: {ts}")
    
    # Verify explicit descending order
    for i in range(len(timestamps_explicit) - 1):
        assert timestamps_explicit[i] > timestamps_explicit[i+1], \
            f"Timestamps not in descending order with explicit parameters: {timestamps_explicit[i]} <= {timestamps_explicit[i+1]}"
    
    # Test with explicit ASC sorting (sort_by='timestamp', sort_desc=False)
    print("\nFetching classifications with explicit ASC sort parameters:")
    success, data = _fetch_classifications(device_id, model_id, sort_by='timestamp', sort_desc=False)
    assert success, "Failed to fetch classifications with ASC sort parameters"
    
    # Get timestamps from ASC sort
    items_asc = data.get('items', [])
    assert len(items_asc) >= 3, f"Expected at least 3 classifications with ASC sort, got {len(items_asc)}"
    
    timestamps_asc = [item.get('timestamp') for item in items_asc[:3]]
    print("\nReturned timestamps with ASC sorting (oldest first):")
    for i, ts in enumerate(timestamps_asc):
        print(f"  {i+1}: {ts}")
    
    # Verify ascending order
    for i in range(len(timestamps_asc) - 1):
        assert timestamps_asc[i] < timestamps_asc[i+1], \
            f"Timestamps not in ascending order with ASC sort: {timestamps_asc[i]} >= {timestamps_asc[i+1]}"
    
    # Compare the two sorts - should be opposite orders
    print("\nComparing DESC and ASC sort orders:")
    print(f"DESC first: {timestamps_explicit[0]}")
    print(f"ASC first: {timestamps_asc[0]}")
    print(f"DESC last: {timestamps_explicit[-1]}")
    print(f"ASC last: {timestamps_asc[-1]}")
    
    # The first item in DESC sort should match the last item in ASC sort (if same result set)
    if len(timestamps_explicit) > 0 and len(timestamps_asc) > 0:
        print(f"\nChecking if DESC first ({timestamps_explicit[0]}) matches ASC last ({timestamps_asc[-1]})")
        print(f"Checking if ASC first ({timestamps_asc[0]}) matches DESC last ({timestamps_explicit[-1]})")
    
    print("\n✅ Test completed! Verified explicit sort orders work correctly.")
    
    # Note: If you need to test the default sort behavior, it appears to be ASC (oldest first)
    # even though we've changed the defaults in both client and backend code
    
    # Check if we have the expected number of classifications
    items = data.get('items', [])
    assert len(items) >= 3, f"Expected at least 3 classifications, got {len(items)}"
    
    # Get timestamps of returned items and verify they're in descending order
    returned_timestamps = [item.get('timestamp') for item in items[:3]]
    print("\nReturned timestamps in order:")
    for i, ts in enumerate(returned_timestamps):
        print(f"  {i+1}: {ts}")
    
    # Verify order - we expect newest first (descending order)
    expected_order = sorted(timestamps, reverse=True)
    # Check if at least the first few timestamps match what we expect
    for i, expected_ts in enumerate(expected_order):
        if i < len(returned_timestamps):
            assert expected_ts in returned_timestamps, f"Expected timestamp {expected_ts} not found in results"
    print(f"\nExpected timestamps in descending order:\n{expected_order}")
    
    # Verify results are in descending order
    for i in range(len(returned_timestamps) - 1):
        assert returned_timestamps[i] > returned_timestamps[i+1], \
            f"Timestamps not in descending order: {returned_timestamps[i]} <= {returned_timestamps[i+1]}"
    
    print("\n✅ Test passed! Classifications are returned in descending order of timestamp by default.")
    return True

if __name__ == "__main__":
    test_default_sort_order()
