"""
tests/test_watcher.py — Unit tests for the GhostBackup file watcher

Run with:  pytest backend/tests/test_watcher.py -v
"""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from watcher import _SourceHandler, DEBOUNCE_SECONDS, COOLDOWN_SECONDS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_event(src_path: str):
    """Create a minimal mock file-system event."""
    ev = MagicMock()
    ev.is_directory = False
    ev.src_path     = src_path
    return ev


# ── Tests ────────────────────────────────────────────────────────────────────

class TestWatcherDebounce:
    def test_watcher_debounce(self):
        """Verify rapid changes are debounced to a single callback."""
        triggered = []

        handler = _SourceHandler(
            label="Test",
            source_path="/tmp/test",
            exclude_patterns=[],
            on_trigger=lambda label: triggered.append(label),
        )

        # Fire many rapid events
        for i in range(20):
            handler.on_any_event(_make_event(f"/tmp/test/file_{i}.txt"))

        # At this point the debounce timer is running but has NOT fired yet
        assert len(triggered) == 0

        # Wait for the debounce period to elapse (add a small buffer)
        time.sleep(DEBOUNCE_SECONDS + 1)

        # Should have fired exactly once despite 20 events
        assert len(triggered) == 1
        assert triggered[0] == "Test"

        handler.cancel()

    def test_watcher_cooldown(self):
        """Verify cooldown period suppresses a second trigger."""
        triggered = []

        handler = _SourceHandler(
            label="Test",
            source_path="/tmp/test",
            exclude_patterns=[],
            on_trigger=lambda label: triggered.append(label),
        )

        # Simulate the first trigger firing
        handler._fire()
        assert len(triggered) == 1

        # Immediately fire again — should be suppressed by cooldown
        handler._fire()
        assert len(triggered) == 1  # still 1, second was suppressed

        handler.cancel()

    def test_watcher_timezone_consistency(self):
        """Verify _last_triggered_at uses UTC."""
        triggered = []

        handler = _SourceHandler(
            label="Test",
            source_path="/tmp/test",
            exclude_patterns=[],
            on_trigger=lambda label: triggered.append(label),
        )

        handler._fire()

        assert handler._last_triggered_at is not None
        assert handler._last_triggered_at.tzinfo is not None
        assert handler._last_triggered_at.tzinfo == timezone.utc

        handler.cancel()


class TestWatcherExclusions:
    def test_ghosttmp_files_ignored(self):
        """Verify .ghosttmp files don't trigger the watcher."""
        triggered = []

        handler = _SourceHandler(
            label="Test",
            source_path="/tmp/test",
            exclude_patterns=[],
            on_trigger=lambda label: triggered.append(label),
        )

        handler.on_any_event(_make_event("/tmp/test/backup.xlsx.ghosttmp"))

        # No pending events should be queued
        assert handler._pending_count == 0

        handler.cancel()

    def test_excluded_patterns_ignored(self):
        """Verify excluded patterns don't trigger the watcher."""
        triggered = []

        handler = _SourceHandler(
            label="Test",
            source_path="/tmp/test",
            exclude_patterns=["*.tmp", "Thumbs.db"],
            on_trigger=lambda label: triggered.append(label),
        )

        handler.on_any_event(_make_event("/tmp/test/scratch.tmp"))
        handler.on_any_event(_make_event("/tmp/test/Thumbs.db"))

        assert handler._pending_count == 0

        handler.cancel()
