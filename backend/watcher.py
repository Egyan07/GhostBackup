"""
watcher.py — GhostBackup Real-Time File Watcher  (Phase 3)

Uses the watchdog library to watch all enabled source folders for filesystem
events and triggers incremental backups automatically, without waiting for the
scheduled 08:00 run.

Design:
  - One watchdog observer, one event handler per source folder
  - Debounce: file changes are collected into a pending set; after DEBOUNCE_SECONDS
    of silence on that source, a single incremental backup is triggered for that
    source only — not the full job
  - Cooldown: after a watcher-triggered run completes, COOLDOWN_SECONDS must pass
    before the same source can trigger another run — prevents thrash on bulk saves
  - Excluded patterns (from config) are respected at the event level
  - Events on .ghosttmp files are ignored (our own write safety pattern)
  - Thread-safe: watchdog runs in a background thread; backup is dispatched via
    asyncio.run_coroutine_threadsafe into the main event loop

Public API (used by api.py):
  FileWatcher(config, trigger_fn, loop)
    trigger_fn: async callable(sources=[label]) — same signature as run_backup_job
    loop:       the running asyncio event loop

  watcher.start()        → start watching all enabled sources
  watcher.stop()         → stop observer + cancel all debounce timers
  watcher.status()       → dict {running, sources: [{label, path, pending, last_triggered}]}
  watcher.reload_sources()  → re-read config and add/remove watched paths
"""

import asyncio
import fnmatch
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Coroutine, Optional

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from config import ConfigManager

logger = logging.getLogger("watcher")

# ── Tuning constants ───────────────────────────────────────────────────────────
DEBOUNCE_SECONDS = 15    # wait this long after last change before triggering
COOLDOWN_SECONDS = 120   # min gap between two watcher-triggered runs per source


class _SourceHandler(FileSystemEventHandler):
    """
    Handles watchdog events for a single source folder.
    Accumulates changed file paths and fires a debounced backup trigger.
    """

    def __init__(
        self,
        label: str,
        source_path: str,
        exclude_patterns: list[str],
        on_trigger: Callable[[str], None],   # sync callback into asyncio
    ):
        super().__init__()
        self.label           = label
        self.source_path     = source_path
        self.exclude_patterns = exclude_patterns
        self._on_trigger     = on_trigger

        self._pending: set[str] = set()
        self._lock              = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self._last_triggered: Optional[float] = None
        self._pending_count  = 0   # snapshot for status()

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Ignore directory events and our own temp files
        if event.is_directory:
            return
        src = getattr(event, "src_path", "") or ""
        if src.endswith(".ghosttmp"):
            return

        # Exclusion check
        name = Path(src).name
        for pat in self.exclude_patterns:
            if fnmatch.fnmatch(name, pat):
                return

        with self._lock:
            self._pending.add(src)
            self._pending_count = len(self._pending)

            # Reset debounce timer
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                DEBOUNCE_SECONDS, self._fire
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _fire(self) -> None:
        """Called by debounce timer on the watchdog thread."""
        with self._lock:
            count = len(self._pending)
            self._pending.clear()
            self._pending_count = 0

        # Cooldown check
        now = time.monotonic()
        if self._last_triggered and (now - self._last_triggered) < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - (now - self._last_triggered))
            logger.debug(
                f"[{self.label}] Watcher trigger suppressed — cooldown ({remaining}s remaining)"
            )
            return

        self._last_triggered = now
        logger.info(f"[{self.label}] Watcher detected {count} change(s) — triggering backup")
        self._on_trigger(self.label)

    def cancel(self) -> None:
        with self._lock:
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()

    def status(self) -> dict:
        return {
            "label":            self.label,
            "path":             self.source_path,
            "pending_changes":  self._pending_count,
            "last_triggered":   (
                time.strftime(
                    "%H:%M:%S", time.localtime(
                        time.time() - (time.monotonic() - self._last_triggered)
                    )
                ) if self._last_triggered else None
            ),
        }


class FileWatcher:
    """
    Manages a watchdog Observer that watches all enabled source folders.
    Triggers incremental backups on the main asyncio loop via run_coroutine_threadsafe.
    """

    def __init__(
        self,
        config: ConfigManager,
        trigger_fn: Callable[..., Coroutine],   # async run_backup_job(sources=[label])
        loop: asyncio.AbstractEventLoop,
    ):
        self._config      = config
        self._trigger_fn  = trigger_fn
        self._loop        = loop
        self._observer    = Observer()
        self._handlers:   dict[str, _SourceHandler] = {}   # label → handler
        self._running     = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            logger.warning("FileWatcher already running — call reload_sources() to update")
            return
        self._register_sources()
        self._observer.start()
        self._running = True
        logger.info(
            f"FileWatcher started — watching {len(self._handlers)} source(s)"
        )

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
        """
        Re-read config sources and update the observer in-place.
        Called when the user adds or removes a source folder at runtime.
        Stops and restarts the observer — safe because Observer is re-created.
        """
        if self._running:
            self.stop()
        self._observer = Observer()
        self.start()
        logger.info("FileWatcher reloaded — sources updated")

    # ── Registration ──────────────────────────────────────────────────────────

    def _register_sources(self) -> None:
        patterns = self._config.exclude_patterns
        for source in self._config.get_enabled_sources():
            label = source.get("label") or source.get("name", "?")
            path  = source.get("path", "")
            if not path or not Path(path).exists():
                logger.warning(
                    f"[{label}] Skipping watcher — path not found: {path}"
                )
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

    # ── Dispatch into asyncio ─────────────────────────────────────────────────

    def _dispatch(self, label: str) -> None:
        """
        Called from the watchdog thread. Submits the async backup coroutine
        onto the main event loop thread-safely.
        """
        asyncio.run_coroutine_threadsafe(
            self._trigger_fn(full=False, sources=[label]),
            self._loop,
        )

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "running":  self._running,
            "sources":  [h.status() for h in self._handlers.values()],
            "debounce_seconds": DEBOUNCE_SECONDS,
            "cooldown_seconds": COOLDOWN_SECONDS,
        }
