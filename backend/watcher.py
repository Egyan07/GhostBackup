"""
watcher.py — GhostBackup Real-Time File Watcher

Watches configured source folders for file changes and triggers incremental
backup runs after a debounce period. Uses a cooldown to prevent repeated
triggers during sustained write bursts (e.g. large SharePoint syncs).
"""

import asyncio
import fnmatch
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine, Optional

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from config import ConfigManager

logger = logging.getLogger("watcher")

DEBOUNCE_SECONDS = 15
COOLDOWN_SECONDS = 120


class _SourceHandler(FileSystemEventHandler):
    def __init__(
        self,
        label: str,
        source_path: str,
        exclude_patterns: list[str],
        on_trigger: Callable[[str], None],
    ):
        super().__init__()
        self.label            = label
        self.source_path      = source_path
        self.exclude_patterns = exclude_patterns
        self._on_trigger      = on_trigger

        self._pending: set[str]                   = set()
        self._lock                                 = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self._last_triggered_mono: Optional[float] = None
        self._last_triggered_at: Optional[datetime] = None
        self._pending_count = 0

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = getattr(event, "src_path", "") or ""
        if src.endswith(".ghosttmp"):
            return
        name = Path(src).name
        for pat in self.exclude_patterns:
            if fnmatch.fnmatch(name, pat):
                return
        with self._lock:
            self._pending.add(src)
            self._pending_count = len(self._pending)
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(DEBOUNCE_SECONDS, self._fire)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _fire(self) -> None:
        with self._lock:
            count = len(self._pending)
            self._pending.clear()
            self._pending_count = 0

        now = time.monotonic()
        if (
            self._last_triggered_mono is not None
            and (now - self._last_triggered_mono) < COOLDOWN_SECONDS
        ):
            remaining = int(COOLDOWN_SECONDS - (now - self._last_triggered_mono))
            logger.debug(
                f"[{self.label}] Watcher trigger suppressed — cooldown ({remaining}s remaining)"
            )
            return

        self._last_triggered_mono = now
        self._last_triggered_at   = datetime.now(timezone.utc)
        logger.info(f"[{self.label}] Watcher detected {count} change(s) — triggering backup")
        self._on_trigger(self.label)

    def cancel(self) -> None:
        with self._lock:
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()

    def status(self) -> dict:
        return {
            "label":           self.label,
            "path":            self.source_path,
            "pending_changes": self._pending_count,
            "last_triggered":  (
                self._last_triggered_at.strftime("%H:%M:%S")
                if self._last_triggered_at else None
            ),
        }


class FileWatcher:
    def __init__(
        self,
        config: ConfigManager,
        trigger_fn: Callable[..., Coroutine],
        loop: asyncio.AbstractEventLoop,
    ):
        self._config     = config
        self._trigger_fn = trigger_fn
        self._loop       = loop
        self._loop_lock  = threading.Lock()
        self._observer   = Observer()
        self._handlers:  dict[str, _SourceHandler] = {}
        self._running    = False

    def update_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Allow api.py to refresh the event loop reference after restart."""
        with self._loop_lock:
            self._loop = loop

    def start(self) -> None:
        if self._running:
            logger.warning("FileWatcher already running — call reload_sources() to update")
            return
        self._register_sources()
        self._observer.start()
        self._running = True
        logger.info(f"FileWatcher started — watching {len(self._handlers)} source(s)")

    def stop(self) -> None:
        if not self._running:
            return
        for h in self._handlers.values():
            h.cancel()
        self._observer.stop()
        self._observer.join(timeout=5)
        self._running  = False
        self._handlers = {}
        logger.info("FileWatcher stopped")

    def reload_sources(self) -> None:
        if self._running:
            self.stop()
        self._observer = Observer()
        self.start()
        logger.info("FileWatcher reloaded — sources updated")

    def _register_sources(self) -> None:
        patterns = self._config.exclude_patterns
        for source in self._config.get_enabled_sources():
            label = source.get("label") or source.get("name", "?")
            path  = source.get("path", "")
            if not path or not Path(path).exists():
                logger.warning(f"[{label}] Skipping watcher — path not found: {path}")
                continue
            handler = _SourceHandler(
                label            = label,
                source_path      = path,
                exclude_patterns = patterns,
                on_trigger       = self._dispatch,
            )
            self._observer.schedule(handler, path, recursive=True)
            self._handlers[label] = handler
            logger.info(f"[{label}] Watching: {path}")

    def _dispatch(self, label: str) -> None:
        """Schedule a backup coroutine on the asyncio loop from this watchdog thread."""
        with self._loop_lock:
            loop = self._loop

        if loop is None:
            logger.error(f"[{label}] Cannot dispatch watcher trigger — no event loop")
            return
        if loop.is_closed():
            logger.error(f"[{label}] Cannot dispatch watcher trigger — event loop is closed")
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self._trigger_fn(full=False, sources=[label]),
                loop,
            )
        except RuntimeError as e:
            logger.error(f"[{label}] Watcher dispatch failed: {e}")

    def status(self) -> dict:
        return {
            "running":          self._running,
            "sources":          [h.status() for h in self._handlers.values()],
            "debounce_seconds": DEBOUNCE_SECONDS,
            "cooldown_seconds": COOLDOWN_SECONDS,
        }
