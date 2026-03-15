"""
syncer.py — GhostBackup Local SSD Syncer  (Phase 2)

Replaces puller.py + writer.py + auth.py entirely.
No cloud API, no tokens, no network — pure local filesystem operations.

Core design:
  - Two-tier change detection:
      1. mtime check (nanoseconds, near-zero cost)      → skip if unchanged
      2. xxhash64 of source file                         → compare vs manifest cache
      3. Copy only if hash differs (or forced full run)
  - Chunked copy with progress callbacks for live UI
  - .ghosttmp write-then-rename for crash safety
  - Post-copy xxhash verify (optional, config.verify_checksums)
  - ThreadPoolExecutor for parallel copies across sources
  - SSD availability check before each run
  - Locked-file / permission-error graceful handling
  - Versioned backups: <ssd>/<source_label>/<rel_path>.<run_id>
  - Pruning: remove backup versions older than retention policy
"""

import asyncio
import fnmatch
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import xxhash
import psutil

from config import ConfigManager
from manifest import ManifestDB

logger = logging.getLogger("syncer")

# Max extended path length on Windows
WIN_PATH_PREFIX = "\\\\?\\"


# ── SSD health ────────────────────────────────────────────────────────────────

def get_ssd_status(ssd_path: str) -> dict:
    """
    Return drive health dict for the /ssd/status endpoint and dashboard.
    Never raises — always returns a dict with a 'status' key.
    """
    if not ssd_path:
        return {"status": "not_configured", "error": "No SSD path set in config"}

    p = Path(ssd_path)
    try:
        if not p.exists():
            return {
                "status": "disconnected",
                "path":   ssd_path,
                "error":  "Path does not exist — drive may be unplugged",
            }

        usage   = shutil.disk_usage(ssd_path)
        used_gb = (usage.total - usage.free) / 1024 ** 3
        free_gb = usage.free  / 1024 ** 3
        tot_gb  = usage.total / 1024 ** 3

        # Try to determine filesystem type via psutil partitions
        fs_type = "unknown"
        try:
            for part in psutil.disk_partitions(all=True):
                if ssd_path.lower().startswith(part.mountpoint.lower()):
                    fs_type = part.fstype
                    break
        except Exception:
            pass

        return {
            "status":       "ok",
            "path":         ssd_path,
            "used_gb":      round(used_gb, 2),
            "available_gb": round(free_gb, 2),
            "total_gb":     round(tot_gb,  2),
            "fs_type":      fs_type,
        }

    except PermissionError:
        return {"status": "disconnected", "path": ssd_path,
                "error": "Permission denied — cannot read drive"}
    except Exception as e:
        return {"status": "error", "path": ssd_path, "error": str(e)}


# ── File utilities ────────────────────────────────────────────────────────────

def _hash_file(path: Path, chunk_bytes: int = 65536) -> str:
    """Return xxhash64 hex digest of a file. ~10 GB/s on modern hardware."""
    h = xxhash.xxh64()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _extended_path(p: Path) -> str:
    """Return \\\\?\\-prefixed path string for Windows long-path support."""
    s = str(p.resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return WIN_PATH_PREFIX + s
    return s


def _should_exclude(rel_path: str, patterns: list[str]) -> bool:
    """
    Return True if rel_path matches any exclusion pattern.
    Checks against:
      - the filename only  (e.g. Thumbs.db, *.tmp)
      - the full relative path  (e.g. dist/*)
      - every path component  (e.g. node_modules, .git, __pycache__)
        so that folder-name patterns exclude entire subtrees
    """
    p    = Path(rel_path)
    name = p.name
    parts = p.parts   # all components: ('node_modules', 'electron', 'libGLESv2.dll')

    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
        if fnmatch.fnmatch(rel_path, pat):
            return True
        # Match any folder component so 'node_modules' excludes everything inside it
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


# ── Core syncer ───────────────────────────────────────────────────────────────

class LocalSyncer:
    """
    Scans source folders, detects changed files via mtime + xxhash,
    and copies only changed files to the SSD destination.
    """

    def __init__(self, config: ConfigManager, manifest: ManifestDB):
        self._config   = config
        self._manifest = manifest

    # ── Pre-flight ────────────────────────────────────────────────────────────

    def check_ssd(self) -> dict:
        return get_ssd_status(self._config.ssd_path)

    def _hash_file_direct(self, path) -> str:
        """Public wrapper around module-level _hash_file — used by retry logic in api.py."""
        return _hash_file(Path(path), self._config.chunk_size_bytes)

    def assert_ssd_ready(self) -> None:
        """Raise RuntimeError if SSD is not accessible."""
        status = self.check_ssd()
        if status["status"] != "ok":
            raise RuntimeError(
                f"SSD not ready: {status.get('error', status['status'])}"
            )

    # ── Scan: detect changed files ────────────────────────────────────────────

    def scan_source(
        self,
        source: dict,
        force_full: bool = False,
    ) -> tuple[list[dict], int]:
        """
        Walk a source folder. Return (changed_files, skipped_count).

        Two-tier detection:
          Step 1 — compare mtime vs manifest cache (nanosecond precision).
                   If mtime unchanged → file not changed → skip (no disk read).
          Step 2 — if mtime changed, compute xxhash of source file.
                   If hash unchanged → content identical → skip.
          Remaining files → need copying.

        Returns list of file_meta dicts, each with:
          source_label, name, original_path, size, mtime, xxhash, rel_path
        """
        label    = source.get("label") or source.get("name", "?")
        src_path = Path(source["path"])

        if not src_path.exists():
            raise FileNotFoundError(f"Source folder not found: {src_path}")

        changed  = []
        skipped  = 0
        patterns = self._config.exclude_patterns
        max_size = self._config.max_file_size_bytes

        for entry in src_path.rglob("*"):
            if not entry.is_file():
                continue

            rel = str(entry.relative_to(src_path))

            # Exclusion check
            if _should_exclude(rel, patterns):
                skipped += 1
                continue

            try:
                stat = entry.stat()
            except OSError:
                skipped += 1
                continue

            size  = stat.st_size
            mtime = stat.st_mtime   # float seconds

            # Size gate
            if size > max_size:
                logger.warning(f"Skipping oversized file ({size/(1024**3):.1f} GB): {rel}")
                skipped += 1
                continue

            if not force_full:
                cached = self._manifest.get_file_hash(str(entry))
                if cached and abs(cached["mtime"] - mtime) < 0.001 and cached["size"] == size:
                    # mtime + size match → safe to skip without hashing
                    skipped += 1
                    continue

            # Need to hash
            try:
                file_hash = _hash_file(entry, self._config.chunk_size_bytes)
            except (OSError, PermissionError) as e:
                logger.warning(f"Cannot hash {rel}: {e}")
                skipped += 1
                continue

            if not force_full:
                cached = self._manifest.get_file_hash(str(entry))
                if cached and cached["xxhash"] == file_hash:
                    # Content identical despite mtime change — update cache, skip copy
                    self._manifest.save_file_hash(str(entry), file_hash, mtime, size)
                    skipped += 1
                    continue

            changed.append({
                "source_label":  label,
                "name":          entry.name,
                "original_path": str(entry),
                "rel_path":      rel,
                "size":          size,
                "mtime":         mtime,
                "xxhash":        file_hash,
            })

        logger.info(
            f"[{label}] Scan complete — {len(changed)} to copy, {skipped} skipped"
        )
        return changed, skipped

    # ── Copy one file ─────────────────────────────────────────────────────────

    def copy_file(
        self,
        file_meta: dict,
        run_id: int,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Copy a single file to the SSD. Returns the backup path string.

        Strategy:
          1. Build destination path:  <ssd>/<source_label>/<rel_path>
          2. Write to <dest>.ghosttmp (crash-safe)
          3. Rename to final path (atomic on same volume)
          4. Optionally verify post-copy xxhash (config.verify_checksums)
          5. Update manifest hash cache
        """
        ssd_root    = Path(self._config.ssd_path)
        label       = file_meta["source_label"]
        rel_path    = file_meta["rel_path"]
        src         = Path(file_meta["original_path"])
        dest        = ssd_root / _sanitise_label(label) / rel_path
        dest_tmp    = dest.with_suffix(dest.suffix + ".ghosttmp")

        dest.parent.mkdir(parents=True, exist_ok=True)

        chunk = self._config.chunk_size_bytes
        try:
            with open(_extended_path(src), "rb") as fsrc, \
                 open(_extended_path(dest_tmp), "wb") as fdst:
                copied = 0
                while True:
                    buf = fsrc.read(chunk)
                    if not buf:
                        break
                    fdst.write(buf)
                    copied += len(buf)
                    if on_progress:
                        on_progress(len(buf))
        except PermissionError as e:
            dest_tmp.unlink(missing_ok=True)
            raise RuntimeError(f"File locked or permission denied: {src.name} — {e}")
        except OSError as e:
            dest_tmp.unlink(missing_ok=True)
            raise RuntimeError(f"OS error copying {src.name}: {e}")

        # Atomic rename (same volume guaranteed — both on SSD)
        dest_tmp.replace(dest)

        # Post-copy verify
        if self._config.verify_checksums:
            dest_hash = _hash_file(dest, chunk)
            if dest_hash != file_meta["xxhash"]:
                dest.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Checksum mismatch after copy: {src.name} "
                    f"(src={file_meta['xxhash'][:8]}… dest={dest_hash[:8]}…)"
                )

        # Copy timestamps (best-effort)
        try:
            shutil.copystat(_extended_path(src), _extended_path(dest))
        except OSError:
            pass

        # Update hash cache — future runs can skip this file if unchanged
        self._manifest.save_file_hash(
            file_meta["original_path"],
            file_meta["xxhash"],
            file_meta["mtime"],
            file_meta["size"],
        )

        return str(dest)

    # ── Restore ───────────────────────────────────────────────────────────────

    def restore_files(
        self,
        files: list[dict],
        destination: str,
        on_progress: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        """
        Copy backup files back to a local destination folder.
        Returns summary dict {restored, failed, errors}.
        """
        dest_root = Path(destination)
        dest_root.mkdir(parents=True, exist_ok=True)

        restored = 0
        failed   = 0
        errors   = []
        chunk    = self._config.chunk_size_bytes

        for f in files:
            src           = Path(f.get("backup_path", ""))
            original_path = f.get("original_path", "")
            label         = f.get("source_label", "")

            # Derive rel_path from original_path by stripping the source root
            # e.g. original = C:\My Projects\foo\bar.py, source root = C:\My Projects
            # → rel_path = foo\bar.py  → restores as dest\foo\bar.py
            rel_path = None
            if original_path:
                source_root = next(
                    (s.get("path", "") for s in self._config.get_enabled_sources()
                     if s.get("label") == label or s.get("name") == label),
                    None,
                )
                if source_root:
                    try:
                        rel_path = Path(original_path).relative_to(source_root)
                    except ValueError:
                        pass

            # Fall back to just the filename if we can't derive relative path
            if not rel_path:
                rel_path = Path(f.get("name", src.name))

            dest = dest_root / rel_path

            if not src.exists():
                errors.append({"file": str(rel_path), "error": "Backup file not found on SSD"})
                failed += 1
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(_extended_path(src), "rb") as fsrc, \
                     open(_extended_path(dest), "wb") as fdst:
                    while True:
                        buf = fsrc.read(chunk)
                        if not buf:
                            break
                        fdst.write(buf)
                        if on_progress:
                            on_progress(str(rel_path), len(buf))
                restored += 1
            except Exception as e:
                errors.append({"file": str(rel_path), "error": str(e)})
                failed += 1

        return {"restored": restored, "failed": failed, "errors": errors}

    # ── Pruning ───────────────────────────────────────────────────────────────

    def prune_old_backups(
        self,
        daily_days: int,
        weekly_days: int,
        guard_days: int,
    ) -> int:
        """
        Delete SSD backup files older than the retention policy.
        guard_days is a hard minimum — files newer than this are NEVER deleted.
        Returns count of files removed.
        """
        guard_cutoff = datetime.utcnow() - timedelta(days=guard_days)
        daily_cutoff = datetime.utcnow() - timedelta(days=daily_days)
        removed      = 0

        for source in self._config.get_enabled_sources():
            label = source.get("label") or source.get("name", "")
            old_files = self._manifest.get_backup_files_for_prune(
                label, daily_cutoff.isoformat()
            )
            for f in old_files:
                backed_up = datetime.fromisoformat(
                    f.get("started_at", datetime.utcnow().isoformat())
                )
                if backed_up > guard_cutoff:
                    continue    # inside safety window
                bp = Path(f["backup_path"])
                if bp.exists():
                    try:
                        bp.unlink()
                        removed += 1
                    except OSError as e:
                        logger.warning(f"Could not prune {bp}: {e}")

        logger.info(f"Prune complete — {removed} files removed")
        return removed


# ── Utilities ─────────────────────────────────────────────────────────────────

def _sanitise_label(label: str) -> str:
    """Make a source label safe to use as a directory name."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ ")
    s = "".join(c if c in keep else "_" for c in label).strip()
    return s or "source"
