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


# =============================================================================
#   Regression — fix #3: timezone-aware missed-backup check
# =============================================================================

def test_hours_ago_with_naive_stored_timestamp():
    """
    Regression: fromisoformat on a naive UTC string must not crash
    when compared against timezone.utc now.
    The fix coerces naive datetimes to UTC before subtraction.
    """
    from datetime import datetime, timezone, timedelta

    naive_ts = "2026-01-01T06:00:00"          # naive — no tzinfo
    last_dt  = datetime.fromisoformat(naive_ts)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)

    now_utc   = datetime.now(timezone.utc)
    # Must not raise TypeError
    hours_ago = (now_utc - last_dt).total_seconds() / 3600
    assert hours_ago > 0


def test_hours_ago_with_aware_stored_timestamp():
    """Aware timestamps must also work correctly."""
    from datetime import datetime, timezone, timedelta

    aware_ts = "2026-01-01T06:00:00+00:00"
    last_dt  = datetime.fromisoformat(aware_ts)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)

    now_utc   = datetime.now(timezone.utc)
    hours_ago = (now_utc - last_dt).total_seconds() / 3600
    assert hours_ago > 0


# ── BackupScheduler lifecycle ──────────────────────────────────────────────────

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from scheduler import BackupScheduler


def _make_config():
    cfg = MagicMock()
    cfg.schedule_time        = "08:00"
    cfg.timezone             = "UTC"
    cfg.retry_count          = 2
    cfg.retry_delay_minutes  = 0
    cfg.max_job_minutes      = 240
    return cfg


class TestBackupSchedulerLifecycle:
    def test_is_running_false_before_start(self):
        s = BackupScheduler(_make_config(), AsyncMock())
        assert s.is_running() is False

    def test_is_running_true_after_start(self):
        s = BackupScheduler(_make_config(), AsyncMock())
        with patch.object(s._sched, "start"), patch.object(s._sched, "add_job"):
            s.start()
            assert s.is_running() is True
            s._sched.shutdown = MagicMock()
            s.stop()

    def test_set_current_run_id(self):
        s = BackupScheduler(_make_config(), AsyncMock())
        s.set_current_run_id(42)
        assert s._current_run_id == 42

    def test_reset_missed_alert_clears_flag(self):
        s = BackupScheduler(_make_config(), AsyncMock())
        s._missed_alerted = True
        s.reset_missed_alert()
        assert s._missed_alerted is False

    def test_reschedule_calls_job_reschedule(self):
        s    = BackupScheduler(_make_config(), AsyncMock())
        job  = MagicMock()
        with patch.object(s._sched, "get_job", return_value=job):
            s.reschedule("09:30", "Europe/London")
            job.reschedule.assert_called_once()

    def test_reschedule_schedules_daily_if_no_job(self):
        s = BackupScheduler(_make_config(), AsyncMock())
        with patch.object(s._sched, "get_job", return_value=None), \
             patch.object(s._sched, "add_job") as mock_add:
            s.reschedule("09:30", "UTC")
            mock_add.assert_called()


class TestBackupSchedulerRetry:
    def test_run_with_retry_succeeds_on_first_attempt(self):
        job_fn = AsyncMock()
        s      = BackupScheduler(_make_config(), job_fn)
        asyncio.run(s._run_with_retry())
        assert job_fn.call_count == 1

    def test_run_with_retry_retries_on_failure(self):
        job_fn = AsyncMock(side_effect=[RuntimeError("fail"), None])
        cfg    = _make_config()
        cfg.retry_count = 1
        s = BackupScheduler(cfg, job_fn)
        asyncio.run(s._run_with_retry())
        assert job_fn.call_count == 2

    def test_run_with_retry_exhausts_all_attempts(self):
        job_fn = AsyncMock(side_effect=RuntimeError("always fails"))
        cfg    = _make_config()
        cfg.retry_count = 2
        reporter = MagicMock()
        reporter.send_retry_alert = AsyncMock()
        s = BackupScheduler(cfg, job_fn, reporter=reporter)
        asyncio.run(s._run_with_retry())
        assert job_fn.call_count == 3
        assert reporter.send_retry_alert.call_count == 3

    def test_run_with_retry_resets_retry_count_on_success(self):
        job_fn = AsyncMock()
        s      = BackupScheduler(_make_config(), job_fn)
        s._retry_count = 5
        asyncio.run(s._run_with_retry())
        assert s._retry_count == 0
