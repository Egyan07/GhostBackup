"""
manifest.py — GhostBackup SQLite Manifest Database  (Phase 2: Local SSD)

Schema changes vs Phase 1 (cloud):
  - delta_tokens table REMOVED (was Graph API-specific)
  - file_hashes table ADDED: stores xxhash + mtime per source path so the
    syncer can detect changes without re-hashing every file on every run
  - files.sha256 renamed to files.xxhash (non-cryptographic, fast)
  - files.library renamed to files.source_label (matches SourceConfig.label)
  - get_file_hash() / save_file_hash() added for incremental change detection
  - get_backup_files_for_prune() added for retention pruning
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("manifest")

DB_PATH = Path("ghostbackup.db")


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
        self._conn.execute("PRAGMA synchronous=NORMAL")   # safe + faster than FULL
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
                    source_label    TEXT NOT NULL,      -- SourceConfig.label
                    name            TEXT NOT NULL,      -- filename only
                    original_path   TEXT NOT NULL,      -- absolute source path
                    backup_path     TEXT NOT NULL,      -- absolute backup path on SSD
                    size            INTEGER NOT NULL DEFAULT 0,
                    xxhash          TEXT,               -- xxhash64 of source file
                    last_modified   REAL,               -- source mtime (float)
                    transferred_at  TEXT NOT NULL
                );

                -- Per-file hash + mtime cache for incremental change detection.
                -- Updated every time a file is successfully backed up.
                -- Keyed on source_path so the syncer can do a fast mtime pre-check,
                -- and only re-hash when mtime has changed.
                CREATE TABLE IF NOT EXISTS file_hashes (
                    source_path     TEXT PRIMARY KEY,
                    xxhash          TEXT NOT NULL,
                    mtime           REAL NOT NULL,      -- os.stat mtime_ns / 1e9
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

                CREATE INDEX IF NOT EXISTS idx_files_run      ON files(run_id);
                CREATE INDEX IF NOT EXISTS idx_files_source   ON files(source_label);
                CREATE INDEX IF NOT EXISTS idx_files_orig     ON files(original_path);
                CREATE INDEX IF NOT EXISTS idx_logs_run       ON logs(run_id);
                CREATE INDEX IF NOT EXISTS idx_logs_level     ON logs(level);
                CREATE INDEX IF NOT EXISTS idx_runs_status    ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_started   ON runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_hashes_path    ON file_hashes(source_path);
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

        # Store folder_summary under both keys so old UI code still works
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

    def mark_run_pruned(self, run_date: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET pruned = 1 WHERE started_at LIKE ?",
                (f"{run_date}%",),
            )
            self._conn.commit()

    # ── File records ──────────────────────────────────────────────────────────

    def record_file(self, run_id: int, file_meta: dict, backup_path: str) -> None:
        """Record a successfully transferred file in the files table."""
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
        Return cached {xxhash, mtime, size} for a source path, or None.
        Called by syncer before hashing — if mtime matches, skip re-hash.
        """
        row = self._conn.execute(
            "SELECT xxhash, mtime, size FROM file_hashes WHERE source_path = ?",
            (source_path,),
        ).fetchone()
        return dict(row) if row else None

    def save_file_hash(self, source_path: str, xxhash: str,
                       mtime: float, size: int) -> None:
        """Upsert the hash cache entry after a successful copy or skip."""
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

    def clear_file_hashes(self, source_label: Optional[str] = None) -> int:
        """
        Clear hash cache entries — forces full re-hash on next run.
        Pass source_label to clear only one folder, or None to clear all.
        """
        with self._lock:
            if source_label:
                # Can't join on source_label directly — clear by path prefix
                # Caller should pass source path prefix instead if needed
                cur = self._conn.execute(
                    "DELETE FROM file_hashes WHERE source_path LIKE ?",
                    (f"%{source_label}%",),
                )
            else:
                cur = self._conn.execute("DELETE FROM file_hashes")
            self._conn.commit()
            return cur.rowcount

    # ── Pruning helpers ───────────────────────────────────────────────────────

    def get_backup_files_for_prune(
        self, source_label: str, older_than_date: str
    ) -> list[dict]:
        """
        Return backup file records older than a cutoff date for a given source.
        Used by the retention pruner to delete stale SSD files.
        """
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
        row = self._conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        # Support both old key (library_summary) and new key (folder_summary)
        summary_raw = run.get("folder_summary") or run.get("library_summary") or "{}"
        run["folder_summary"]  = json.loads(summary_raw)
        run["library_summary"] = run["folder_summary"]   # backwards compat
        run["errors"]          = json.loads(run.get("errors") or "[]")
        return self._format_run(run)

    def get_files(self, run_id: int, library: Optional[str] = None,
                  subfolder: Optional[str] = None) -> list[dict]:
        """library param accepted as source_label for backwards compat."""
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
