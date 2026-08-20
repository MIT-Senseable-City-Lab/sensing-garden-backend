from __future__ import annotations

from decimal import Decimal

import dynamodb


def test_sort_items_by_numeric_field_ascending():
    items = [{"id": "a", "video_size": Decimal("300")}, {"id": "b", "video_size": Decimal("100")}]
    result = dynamodb._sort_items(items, "video_size", False)
    assert [item["id"] for item in result] == ["b", "a"]


def test_sort_items_by_numeric_field_descending():
    items = [{"id": "a", "video_size": Decimal("300")}, {"id": "b", "video_size": Decimal("100")}]
    result = dynamodb._sort_items(items, "video_size", True)
    assert [item["id"] for item in result] == ["a", "b"]


def test_sort_items_does_not_raise_when_field_missing_on_some_rows():
    """video_size/image_size/composite_size are only stamped on archived rows --
    a mixed page (some archived, some flat/legacy) must not crash the sort."""
    items = [
        {"id": "archived", "video_size": Decimal("500")},
        {"id": "flat-no-size"},
        {"id": "also-archived", "video_size": Decimal("100")},
    ]
    result = dynamodb._sort_items(items, "video_size", False)
    # present rows sort ascending by value; missing rows sink to the end regardless
    assert [item["id"] for item in result] == ["also-archived", "archived", "flat-no-size"]


def test_sort_items_missing_field_sorts_last_when_descending():
    items = [
        {"id": "archived", "video_size": Decimal("500")},
        {"id": "flat-no-size"},
    ]
    result = dynamodb._sort_items(items, "video_size", True)
    assert [item["id"] for item in result] == ["archived", "flat-no-size"]


def test_sort_items_no_sort_by_returns_items_unchanged():
    items = [{"id": "a"}, {"id": "b"}]
    assert dynamodb._sort_items(items, None, False) is items


def test_sort_items_by_timestamp_still_works():
    items = [
        {"id": "a", "timestamp": "2026-03-02T00:00:00"},
        {"id": "b", "timestamp": "2026-01-01T00:00:00"},
    ]
    result = dynamodb._sort_items(items, "timestamp", False)
    assert [item["id"] for item in result] == ["b", "a"]
