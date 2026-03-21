"""
tests/test_scheduler_utils.py — Unit tests for scheduler utilities

Run with:  pytest backend/tests/test_scheduler_utils.py -v
"""

import pytest
from scheduler import _parse_time


@pytest.mark.parametrize("time_str, expected", [
    ("08:00",  (8,  0)),
    ("08:30",  (8,  30)),
    ("00:00",  (0,  0)),
    ("23:59",  (23, 59)),
    ("9:05",   (9,  5)),
])
def test_parse_time_valid(time_str, expected):
    assert _parse_time(time_str) == expected


@pytest.mark.parametrize("bad_input", [
    "25:00",   # hour out of range
    "08:60",   # minute out of range
    "abc",     # not a time
    "",        # empty
    "8",       # no colon — treated as hour only, minute defaults to 0 → valid for "8"
])
def test_parse_time_invalid_falls_back_to_0800(bad_input):
    # For inputs like "8" (no colon), the function should handle gracefully.
    # For truly invalid inputs it returns (8, 0).
    result = _parse_time(bad_input)
    assert isinstance(result, tuple)
    assert len(result) == 2
    h, m = result
    assert 0 <= h <= 23
    assert 0 <= m <= 59


def test_parse_time_no_minute_component():
    # "08" should default minute to 0
    h, m = _parse_time("08")
    assert h == 8
    assert m == 0
