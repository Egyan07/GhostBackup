"""
tests/test_watcher.py — Unit tests for the GhostBackup file watcher

Run with:  pytest backend/tests/test_watcher.py -v
"""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import asyncio
from unittest.mock import patch

from watcher import _SourceHandler, FileWatcher, DEBOUNCE_SECONDS, COOLDOWN_SECONDS


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
            debounce_seconds=0.1,
        )

        # Fire many rapid events
        for i in range(20):
            handler.on_any_event(_make_event(f"/tmp/test/file_{i}.txt"))

        # At this point the debounce timer is running but has NOT fired yet
        assert len(triggered) == 0

        # Wait for the debounce period to elapse (add a small buffer)
        time.sleep(0.2)

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


# ── FileWatcher lifecycle ─────────────────────────────────────────────────────

def _make_watcher_config(tmp_path):
    cfg = MagicMock()
    cfg.exclude_patterns = []
    cfg.watcher_debounce_seconds = 0.1
    cfg.watcher_cooldown_seconds = 1
    cfg.get_enabled_sources.return_value = [{"label": "Docs", "path": str(tmp_path)}]
    return cfg


class TestFileWatcherLifecycle:
    def test_start_sets_is_running(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        w    = FileWatcher(cfg, MagicMock(), loop)
        with patch.object(w._observer, "start"), patch.object(w._observer, "stop"), \
             patch.object(w._observer, "join"):
            w.start()
            assert w.is_running is True
            w.stop()
        loop.close()

    def test_stop_clears_is_running(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        w    = FileWatcher(cfg, MagicMock(), loop)
        with patch.object(w._observer, "start"), patch.object(w._observer, "stop"), \
             patch.object(w._observer, "join"):
            w.start()
            w.stop()
            assert w.is_running is False
        loop.close()

    def test_start_twice_is_idempotent(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        w    = FileWatcher(cfg, MagicMock(), loop)
        with patch.object(w._observer, "start") as mock_start, \
             patch.object(w._observer, "stop"), patch.object(w._observer, "join"):
            w.start()
            w.start()  # second call should be a no-op
            assert mock_start.call_count == 1
            w.stop()
        loop.close()

    def test_stop_when_not_running_is_safe(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        w    = FileWatcher(cfg, MagicMock(), loop)
        w.stop()  # should not raise
        loop.close()

    def test_reload_sources_restarts_observer(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        w    = FileWatcher(cfg, MagicMock(), loop)
        with patch.object(w._observer, "start"), patch.object(w._observer, "stop"), \
             patch.object(w._observer, "join"):
            w.start()
            old_observer = w._observer
            w.reload_sources()
            assert w._observer is not old_observer  # new Observer created
            assert w.is_running is True
            w.stop()
        loop.close()

    def test_status_reflects_running_state(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        w    = FileWatcher(cfg, MagicMock(), loop)
        s = w.status()
        assert s["running"] is False
        assert "sources" in s
        loop.close()

    def test_dispatch_with_no_loop_does_not_raise(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        w    = FileWatcher(cfg, MagicMock(), None)
        w._dispatch("Docs")  # loop is None — should log and return

    def test_dispatch_with_closed_loop_does_not_raise(self, tmp_path):
        cfg  = _make_watcher_config(tmp_path)
        loop = asyncio.new_event_loop()
        loop.close()
        w = FileWatcher(cfg, MagicMock(), loop)
        w._dispatch("Docs")  # closed loop — should log and return
