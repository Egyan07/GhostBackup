"""
tests/test_utils.py — Unit tests for backend/utils.py

Run with:  pytest backend/tests/test_utils.py -v
"""

import pytest

from utils import fmt_bytes, fmt_duration


# ── fmt_bytes ─────────────────────────────────────────────────────────────────

class TestFmtBytes:
    def test_zero_bytes(self):
        assert fmt_bytes(0) == "0 B"

    def test_bytes_below_kb(self):
        assert fmt_bytes(512) == "512 B"

    def test_exactly_one_kb(self):
        assert fmt_bytes(1024) == "1.0 KB"

    def test_kilobytes(self):
        assert "KB" in fmt_bytes(2048)

    def test_exactly_one_mb(self):
        assert fmt_bytes(1024 ** 2) == "1.0 MB"

    def test_megabytes(self):
        assert "MB" in fmt_bytes(5 * 1024 ** 2)

    def test_exactly_one_gb(self):
        assert fmt_bytes(1024 ** 3) == "1.0 GB"

    def test_gigabytes(self):
        result = fmt_bytes(2 * 1024 ** 3)
        assert result == "2.0 GB"

    def test_large_value_stays_in_gb(self):
        # 100 GB — should not roll over to a higher unit
        result = fmt_bytes(100 * 1024 ** 3)
        assert "GB" in result

    @pytest.mark.parametrize("b, unit", [
        (0,               "B"),
        (1023,            "B"),
        (1024,            "KB"),
        (1024 ** 2 - 1,   "KB"),
        (1024 ** 2,       "MB"),
        (1024 ** 3 - 1,   "MB"),
        (1024 ** 3,       "GB"),
    ])
    def test_boundary_units(self, b, unit):
        assert unit in fmt_bytes(b)

    def test_returns_string(self):
        assert isinstance(fmt_bytes(1024), str)


# ── fmt_duration ──────────────────────────────────────────────────────────────

class TestFmtDuration:
    def test_zero_returns_em_dash(self):
        assert fmt_duration(0) == "\u2014"

    def test_seconds_only(self):
        assert fmt_duration(45) == "45s"

    def test_exactly_one_minute(self):
        assert fmt_duration(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert fmt_duration(90) == "1m 30s"

    def test_exactly_one_hour(self):
        assert fmt_duration(3600) == "1h 0m 0s"

    def test_hours_minutes_seconds(self):
        assert fmt_duration(3661) == "1h 1m 1s"

    def test_large_value(self):
        # 2h 30m 15s
        assert fmt_duration(2 * 3600 + 30 * 60 + 15) == "2h 30m 15s"

    def test_returns_string(self):
        assert isinstance(fmt_duration(30), str)

    @pytest.mark.parametrize("s, expected", [
        (0,    "\u2014"),
        (1,    "1s"),
        (59,   "59s"),
        (60,   "1m 0s"),
        (3600, "1h 0m 0s"),
        (3661, "1h 1m 1s"),
    ])
    def test_parametrized(self, s, expected):
        assert fmt_duration(s) == expected
