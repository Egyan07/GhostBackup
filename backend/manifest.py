"""
manifest.py — GhostBackup SQLite Manifest Database

Fixes applied:
  - DB_PATH now anchored to __file__ directory (not CWD)        [FIX-P0]
  - get_file_hash() now acquires lock before read               [FIX-P1]
  - clear_file_hashes() rewritten to use path prefix correctly  [FIX-P1]
  - synchronous=FULL for power-loss safety                      [FIX-P3]
  - mark_run_pruned() uses date range instead of LIKE           [FIX-P3]
  - config_audit table added for compliance trail               [FIX-P2]
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("manifest")

# FIX-P0: Anchor DB path to the directory this module lives in, not CWD
DB_PATH = Path(__file__).parent / "ghostbackup.db"


class ManifestDB:
    """
    Thread-safe SQLite wrapper.
    WAL mode allows safe concurrent reads during backup writes.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # FIX-P3: Use FULL sync — NORMAL can lose WAL frames on power cut
        self._conn.execute("PRAGMA synchronous=FULL")
        self._migrate()
        logger.info(f"ManifestDB ready: {db_path}")

    # ── Schema ────────────────────────────────────────────────────────────────

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );

                -- One row per backup run
                CREATE TABLE IF NOT EXISTS runs (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at          TEXT NOT NULL,
                    finished_at         TEXT,
                    status              TEXT NOT NULL DEFAULT 'running',
                    full_backup         INTEGER NOT NULL DEFAULT 0,
                    files_transferred   INTEGER NOT NULL DEFAULT 0,
                    files_skipped       INTEGER NOT NULL DEFAULT 0,
                    files_failed        INTEGER NOT NULL DEFAULT 0,
                    bytes_transferred   INTEGER NOT NULL DEFAULT 0,
                    duration_seconds    INTEGER,
                    folder_summary      TEXT,   -- JSON: per-source-folder stats
                    errors              TEXT,   -- JSON list
                    pruned              INTEGER NOT NULL DEFAULT 0
                );

                -- Every file successfully copied in a run
                CREATE TABLE IF NOT EXISTS files (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          INTEGER NOT NULL REFERENCES runs(id),
                    source_label    TEXT NOT NULL,
                    name            TEXT NOT NULL,
                    original_path   TEXT NOT NULL,
                    backup_path     TEXT NOT NULL,
                    size            INTEGER NOT NULL DEFAULT 0,
                    xxhash          TEXT,
                    last_modified   REAL,
                    transferred_at  TEXT NOT NULL
                );

                -- Per-file hash + mtime cache for incremental change detection
                CREATE TABLE IF NOT EXISTS file_hashes (
                    source_path     TEXT PRIMARY KEY,
                    xxhash          TEXT NOT NULL,
                    mtime           REAL NOT NULL,
                    size            INTEGER NOT NULL,
                    backed_up_at    TEXT NOT NULL
                );

                -- Structured per-run log entries (INFO / WARNING / ERROR)
                CREATE TABLE IF NOT EXISTS logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id      INTEGER NOT NULL REFERENCES runs(id),
                    logged_at   TEXT NOT NULL,
                    level       TEXT NOT NULL,
                    message     TEXT NOT NULL
                );

                -- FIX-P2: Immutable audit trail for configuration changes
                CREATE TABLE IF NOT EXISTS config_audit (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_at  TEXT NOT NULL,
                    field       TEXT NOT NULL,
                    old_value   TEXT,
                    new_value   TEXT NOT NULL,
                    machine     TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_files_run      ON files(run_id);
                CREATE INDEX IF NOT EXISTS idx_files_source   ON files(source_label);
                CREATE INDEX IF NOT EXISTS idx_files_orig     ON files(original_path);
                CREATE INDEX IF NOT EXISTS idx_logs_run       ON logs(run_id);
                CREATE INDEX IF NOT EXISTS idx_logs_level     ON logs(level);
                CREATE INDEX IF NOT EXISTS idx_runs_status    ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_started   ON runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_hashes_path    ON file_hashes(source_path);
                CREATE INDEX IF NOT EXISTS idx_audit_ts       ON config_audit(changed_at DESC);
            """)
            self._conn.commit()

    # ── Run lifecycle ─────────────────────────────────────────────────────────

    def create_run(self, full_backup: bool = False) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO runs (started_at, status, full_backup) VALUES (?, 'running', ?)",
                (datetime.utcnow().isoformat(), int(full_backup)),
            )
            self._conn.commit()
            run_id = cur.lastrowid
            logger.info(f"Run #{run_id} created")
            return run_id

    def finalize_run(self, run_id: int, run_state: dict) -> None:
        started_at  = run_state.get("started_at", "")
        finished_at = run_state.get("finished_at", datetime.utcnow().isoformat())
        status      = run_state.get("status", "unknown")
        try:
            dur = int((
                datetime.fromisoformat(finished_at) -
                datetime.fromisoformat(started_at)
            ).total_seconds())
        except Exception:
            dur = 0

        folder_summary = run_state.get("libraries") or run_state.get("folders", {})

        with self._lock:
            self._conn.execute(
                """UPDATE runs SET
                    finished_at       = ?,
                    status            = ?,
                    files_transferred = ?,
                    files_skipped     = ?,
                    files_failed      = ?,
                    bytes_transferred = ?,
                    duration_seconds  = ?,
                    folder_summary    = ?,
                    errors            = ?
                WHERE id = ?""",
                (
                    finished_at, status,
                    run_state.get("files_transferred", 0),
                    run_state.get("files_skipped",     0),
                    run_state.get("files_failed",      0),
                    run_state.get("bytes_transferred", 0),
                    dur,
                    json.dumps(folder_summary),
                    json.dumps(run_state.get("errors", [])),
                    run_id,
                ),
            )
            self._conn.commit()
        logger.info(f"Run #{run_id} finalized — {status}")

    def mark_run_pruned(self, run_date_start: str, run_date_end: str) -> None:
        """
        FIX-P3: Use explicit date range instead of fragile LIKE matching.
        Caller passes ISO date strings: run_date_start (inclusive), run_date_end (exclusive).
        Example: mark_run_pruned("2026-03-16", "2026-03-17")
        """
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET pruned = 1 WHERE started_at >= ? AND started_at < ?",
                (run_date_start, run_date_end),
            )
            self._conn.commit()

    # ── File records ──────────────────────────────────────────────────────────

    def record_file(self, run_id: int, file_meta: dict, backup_path: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO files
                    (run_id, source_label, name, original_path, backup_path,
                     size, xxhash, last_modified, transferred_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    file_meta.get("source_label", file_meta.get("library", "")),
                    file_meta.get("name", ""),
                    file_meta.get("original_path", file_meta.get("path", "")),
                    backup_path,
                    file_meta.get("size", 0),
                    file_meta.get("xxhash", ""),
                    file_meta.get("mtime"),
                    datetime.utcnow().isoformat(),
                ),
            )
            self._conn.commit()

    # ── File hash cache (incremental detection) ───────────────────────────────

    def get_file_hash(self, source_path: str) -> Optional[dict]:
        """
        FIX-P1: Acquire lock before read to prevent race with concurrent saves.
        Returns cached {xxhash, mtime, size} or None.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT xxhash, mtime, size FROM file_hashes WHERE source_path = ?",
                (source_path,),
            ).fetchone()
        return dict(row) if row else None

    def save_file_hash(self, source_path: str, xxhash: str,
                       mtime: float, size: int) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO file_hashes (source_path, xxhash, mtime, size, backed_up_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(source_path) DO UPDATE SET
                     xxhash       = excluded.xxhash,
                     mtime        = excluded.mtime,
                     size         = excluded.size,
                     backed_up_at = excluded.backed_up_at""",
                (source_path, xxhash, mtime, size, datetime.utcnow().isoformat()),
            )
            self._conn.commit()

    def clear_file_hashes(self, source_path_prefix: Optional[str] = None) -> int:
        """
        FIX-P1: Accepts source_path_prefix (not label) for correct matching.
        Pass source folder path prefix to clear only one source, or None to clear all.
        Example: clear_file_hashes("C:\\\\Projects\\\\Accounts")
        """
        with self._lock:
            if source_path_prefix:
                # Escape LIKE wildcards in the prefix itself
                escaped = source_path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                cur = self._conn.execute(
                    "DELETE FROM file_hashes WHERE source_path LIKE ? ESCAPE '\\'",
                    (f"{escaped}%",),
                )
            else:
                cur = self._conn.execute("DELETE FROM file_hashes")
            self._conn.commit()
            return cur.rowcount

    # ── Pruning helpers ───────────────────────────────────────────────────────

    def get_backup_files_for_prune(
        self, source_label: str, older_than_date: str
    ) -> list[dict]:
        rows = self._conn.execute(
            """SELECT f.backup_path, f.size, r.started_at
               FROM files f
               JOIN runs r ON r.id = f.run_id
               WHERE f.source_label = ?
                 AND r.started_at < ?
                 AND r.pruned = 0
               ORDER BY r.started_at ASC""",
            (source_label, older_than_date),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Config audit trail (FIX-P2) ───────────────────────────────────────────

    def log_config_change(self, field: str, old_value, new_value) -> None:
        """
        Record a configuration change in the immutable audit trail.
        Called by ConfigManager.update() whenever settings are modified.
        """
        import socket
        try:
            machine = socket.gethostname()
        except Exception:
            machine = "unknown"
        with self._lock:
            self._conn.execute(
                """INSERT INTO config_audit (changed_at, field, old_value, new_value, machine)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.utcnow().isoformat(),
                    field,
                    json.dumps(old_value) if old_value is not None else None,
                    json.dumps(new_value),
                    machine,
                ),
            )
            self._conn.commit()

    def get_config_audit(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM config_audit ORDER BY changed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, run_id: int, level: str, message: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO logs (run_id, logged_at, level, message) VALUES (?,?,?,?)",
                (run_id, datetime.utcnow().isoformat(), level.upper(), message),
            )
            self._conn.commit()

    def get_logs(self, run_id: int, level: Optional[str] = None,
                 limit: int = 500) -> list[dict]:
        with self._lock:
            if level:
                rows = self._conn.execute(
                    "SELECT * FROM logs WHERE run_id = ? AND level = ? "
                    "ORDER BY logged_at DESC LIMIT ?",
                    (run_id, level.upper(), limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM logs WHERE run_id = ? "
                    "ORDER BY logged_at DESC LIMIT ?",
                    (run_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Run queries ───────────────────────────────────────────────────────────

    def get_runs(self, limit: int = 30, offset: int = 0) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, started_at, finished_at, status, full_backup,
                          files_transferred, files_failed, bytes_transferred,
                          duration_seconds, pruned
                   FROM runs
                   ORDER BY started_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [self._format_run(dict(r)) for r in rows]

    def get_run(self, run_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if not row:
            return None
        run = dict(row)
        summary_raw = run.get("folder_summary") or run.get("library_summary") or "{}"
        run["folder_summary"]  = json.loads(summary_raw)
        run["library_summary"] = run["folder_summary"]
        run["errors"]          = json.loads(run.get("errors") or "[]")
        return self._format_run(run)

    def get_files(self, run_id: int, library: Optional[str] = None,
                  subfolder: Optional[str] = None) -> list[dict]:
        with self._lock:
            if library and subfolder:
                rows = self._conn.execute(
                    "SELECT * FROM files WHERE run_id = ? AND source_label = ? "
                    "AND original_path LIKE ?",
                    (run_id, library, f"%{subfolder}%"),
                ).fetchall()
            elif library:
                rows = self._conn.execute(
                    "SELECT * FROM files WHERE run_id = ? AND source_label = ?",
                    (run_id, library),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM files WHERE run_id = ?", (run_id,)
                ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_successful_run(self) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE status = 'success' "
                "ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _format_run(run: dict) -> dict:
        run["bytes_human"]    = _fmt_bytes(run.get("bytes_transferred", 0))
        run["duration_human"] = _fmt_duration(run.get("duration_seconds", 0))
        return run

    def close(self) -> None:
        self._conn.close()
        logger.info("ManifestDB closed")


# ── Utilities ─────────────────────────────────────────────────────────────────

def _fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3: return f"{b / 1024 ** 3:.1f} GB"
    if b >= 1024 ** 2: return f"{b / 1024 ** 2:.1f} MB"
    if b >= 1024:      return f"{b / 1024:.1f} KB"
    return f"{b} B"


def _fmt_duration(s: int) -> str:
    if not s: return "—"
    m, sec = divmod(s, 60)
    h, m   = divmod(m, 60)
    if h:  return f"{h}h {m}m {sec}s"
    if m:  return f"{m}m {sec}s"
    return f"{sec}s"
