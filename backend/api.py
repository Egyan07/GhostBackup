"""
api.py — GhostBackup FastAPI Local IPC Server

Runs on http://127.0.0.1:<GHOSTBACKUP_API_PORT> and is spawned by the Electron
main process. All endpoints except /health require an X-API-Key header
matching the token injected via the GHOSTBACKUP_API_TOKEN environment
variable at startup.
"""

import asyncio
import csv
import hmac
import http.client
import io
import json
import logging
import os
import random
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import ConfigManager
from manifest import ManifestDB
from reporter import Reporter, AlertLevel
from scheduler import BackupScheduler
from syncer import LocalSyncer, get_ssd_status
from watcher import FileWatcher
from errors import raise_gb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api")
API_PORT = int(os.getenv("GHOSTBACKUP_API_PORT", "8765"))

_config:     Optional[ConfigManager]   = None
_manifest:   Optional[ManifestDB]      = None
_scheduler:  Optional[BackupScheduler] = None
_reporter:   Optional[Reporter]        = None
_syncer:     Optional[LocalSyncer]     = None
_watcher:    Optional[FileWatcher]     = None
_active_run: Optional[dict]  = None
_run_mutex:  threading.Lock = threading.Lock()  # protects _active_run mutations from thread pool

# ── Rate limiter ──────────────────────────────────────────────────────────────
_limiter = Limiter(key_func=get_remote_address)


# ── Dependency providers ──────────────────────────────────────────────────────

def provide_config() -> Optional[ConfigManager]:
    return _config


def get_manifest() -> Optional[ManifestDB]:
    return _manifest


def get_scheduler() -> Optional[BackupScheduler]:
    return _scheduler


def get_reporter() -> Optional[Reporter]:
    return _reporter


def get_syncer() -> Optional[LocalSyncer]:
    return _syncer


def get_watcher() -> Optional[FileWatcher]:
    return _watcher


async def _desktop_notify(title: str, body: str) -> None:
    """Forward a notification to the Electron notification server on port 8766."""
    def _blocking_notify():
        conn = http.client.HTTPConnection("127.0.0.1", 8766, timeout=2)
        conn.request(
            "POST", "/notify",
            body=json.dumps({"title": title, "body": body}),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": os.getenv("GHOSTBACKUP_API_TOKEN", ""),
            },
        )
        conn.getresponse()
        conn.close()

    try:
        await asyncio.to_thread(_blocking_notify)
    except Exception as e:
        logger.debug(f"Desktop notification failed: {e}")


async def _startup_spot_check(syncer: LocalSyncer, manifest: ManifestDB,
                              reporter: Reporter) -> None:
    """Spot-check 5 random files from the last successful backup at startup."""
    try:
        last_run = manifest.get_latest_successful_run()
        if not last_run:
            logger.info("Startup spot-check: no previous backups — skipping")
            return

        all_files = manifest.get_files(last_run["id"])
        if not all_files:
            return

        sample_size = min(5, len(all_files))
        sample = random.sample(all_files, sample_size)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: syncer.verify_files(sample))

        if result["failed"] or result["missing"]:
            await reporter.alert_and_notify(
                level="critical",
                title="Startup integrity check FAILED",
                body=(
                    f"Spot-checked {sample_size} files from last backup: "
                    f"{result['failed']} corrupt, {result['missing']} missing. "
                    f"Run a full Verify Integrity check immediately."
                ),
                send_email=True,
            )
            logger.error(f"Startup spot-check FAILED: {result}")
        else:
            logger.info(f"Startup spot-check: {result['verified']}/{sample_size} files OK")
    except Exception as e:
        logger.warning(f"Startup spot-check error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _manifest, _scheduler, _reporter, _syncer, _watcher

    logger.info("GhostBackup API starting…")

    _config   = ConfigManager()
    _manifest = ManifestDB()
    _config.set_manifest(_manifest)

    _reporter  = Reporter(_config)
    _syncer    = LocalSyncer(_config, _manifest)
    _scheduler = BackupScheduler(_config, run_backup_job, reporter=_reporter)

    _reporter.set_notify_callback(_desktop_notify)
    _scheduler.set_manifest(_manifest)
    _scheduler.start()

    loop = asyncio.get_running_loop()
    _watcher = FileWatcher(_config, run_backup_job, loop)
    if _config.get_enabled_sources():
        try:
            _watcher.start()
        except Exception as e:
            logger.warning(f"FileWatcher failed to start: {e}")

    if _syncer.encryption_active:
        logger.info("Backup encryption: ACTIVE")
    else:
        logger.warning(
            "Backup encryption: INACTIVE — set GHOSTBACKUP_ENCRYPTION_KEY to enable"
        )

    logger.info(f"GhostBackup API ready on http://127.0.0.1:{API_PORT}")

    # ── Startup spot-check (non-blocking) ────────────────────────────────────
    asyncio.create_task(_startup_spot_check(_syncer, _manifest, _reporter))

    # ── Background SSD health polling ─────────────────────────────────────────
    _ssd_poll_stop = asyncio.Event()

    async def _poll_ssd_health() -> None:
        last_status = None
        while not _ssd_poll_stop.is_set():
            try:
                status = get_ssd_status(_config.ssd_path)
                current = status.get("status")
                if last_status is not None and current != last_status:
                    level: AlertLevel = "warn" if current == "ok" else "error"
                    await _reporter.alert_and_notify(
                        level=level,
                        title="SSD status changed",
                        body=f"Primary SSD status: {last_status} → {current}",
                        send_email=(current != "ok"),
                    )
                last_status = current
            except Exception as poll_err:
                logger.debug(f"SSD poll error: {poll_err}")
            await asyncio.sleep(300)  # 5 minutes

    ssd_poll_task = asyncio.create_task(_poll_ssd_health())

    yield

    _ssd_poll_stop.set()
    ssd_poll_task.cancel()
    try:
        await ssd_poll_task
    except asyncio.CancelledError:
        pass

    logger.info("GhostBackup API shutting down…")
    if _watcher and _watcher.is_running:
        _watcher.stop()
    if _scheduler:
        _scheduler.stop()
    if _manifest:
        _manifest.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="GhostBackup API", version="3.1.0", lifespan=lifespan)

app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: Response(
    content='{"detail":"Rate limit exceeded — slow down"}',
    status_code=429, media_type="application/json",
))
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "file://"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth middleware ───────────────────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Validates X-API-Key against GHOSTBACKUP_API_TOKEN.
    /health and /docs are public so Electron can poll before the UI is shown.
    Falls through in development when no token is configured.
    """
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)

    # CORS preflight — must pass through so CORSMiddleware can add the headers
    if request.method == "OPTIONS":
        return await call_next(request)

    expected_token = os.getenv("GHOSTBACKUP_API_TOKEN", "")
    if expected_token:
        provided = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided, expected_token):
            return Response(
                content='{"detail":"Unauthorized — invalid or missing X-API-Key"}',
                status_code=401,
                media_type="application/json",
            )
    return await call_next(request)


# ── Request / Response Models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    full:    bool      = False
    sources: list[str] = []


class RestoreRequest(BaseModel):
    run_id:      int
    library:     str
    subfolder:   Optional[str] = None
    destination: str
    dry_run:     bool = True


class ConfigUpdateRequest(BaseModel):
    ssd_path:                  Optional[str]       = None
    secondary_ssd_path:        Optional[str]       = None
    schedule_time:             Optional[str]       = None
    timezone:                  Optional[str]       = None
    concurrency:               Optional[int]       = None
    max_file_size_gb:          Optional[int]       = None
    verify_checksums:          Optional[bool]      = None
    exclude_patterns:          Optional[list[str]] = None
    watcher_enabled:           Optional[bool]      = None
    circuit_breaker_threshold: Optional[float]     = None


class SiteRequest(BaseModel):
    label:   Optional[str] = None
    name:    Optional[str] = None
    path:    str
    enabled: bool = True


class SiteUpdateRequest(BaseModel):
    enabled: bool


class SmtpUpdateRequest(BaseModel):
    host:       str
    port:       int
    user:       str
    password:   Optional[str] = None
    recipients: list[str]


class RetentionUpdateRequest(BaseModel):
    daily_days:  int
    weekly_days: int
    guard_days:  int = 7


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_run_state(run_id: int, full: bool) -> dict:
    return {
        "run_id":            run_id,
        "status":            "running",
        "started_at":        datetime.now(timezone.utc).isoformat(),
        "overall_pct":       0,
        "libraries":         {},
        "files_transferred": 0,
        "files_skipped":     0,
        "files_failed":      0,
        "bytes_transferred": 0,
        "errors":            [],
        "feed":              [],
        "speed_bps":         0,
    }


# ── Core backup job ───────────────────────────────────────────────────────────

async def run_backup_job(
    full: bool = False,
    sources: Optional[list[str]] = None,
    cfg: Optional[ConfigManager] = None,
    manifest: Optional[ManifestDB] = None,
    reporter: Optional[Reporter] = None,
    syncer: Optional[LocalSyncer] = None,
    scheduler: Optional[BackupScheduler] = None,
) -> None:
    global _active_run
    # Fall back to module-level globals when called from the scheduler
    # or watcher (which cannot inject dependencies)
    cfg      = cfg      or _config
    manifest = manifest or _manifest
    reporter = reporter or _reporter
    syncer   = syncer   or _syncer
    scheduler = scheduler or _scheduler
    assert cfg is not None and manifest is not None and reporter is not None and syncer is not None

    with _run_mutex:
        if _active_run and _active_run.get("status") == "running":
            logger.warning("Backup already running — skipping duplicate trigger")
            return

        ssd_status = syncer.check_ssd()
        if ssd_status["status"] != "ok":
            err = ssd_status.get("error", "SSD unavailable")
            logger.error(f"Backup aborted — {err}")
            await reporter.alert_and_notify(
                level="error", title="Backup aborted — SSD unavailable",
                body=err, send_email=True,
            )
            return

        run_id      = manifest.create_run(full_backup=full)
        assert run_id is not None
        _active_run = _new_run_state(run_id, full)

    if scheduler:
        scheduler.set_current_run_id(run_id)

    try:
        target_sources = [
            s for s in cfg.get_enabled_sources()
            if not sources or (s.get("label") or s.get("name", "")) in sources
        ]

        if not target_sources:
            raise RuntimeError("No enabled source folders configured")

        total_sources = len(target_sources)
        executor      = ThreadPoolExecutor(max_workers=cfg.concurrency)

        try:
            for idx, source in enumerate(target_sources):
                label = source.get("label") or source.get("name", "?")

                if not Path(source["path"]).exists():
                    _active_run["errors"].append({
                        "library": label,
                        "error":   f"Source folder not found: {source['path']}",
                    })
                    _active_run["libraries"][label] = {
                        "status": "failed", "pct": 0,
                        "files_transferred": 0, "files_failed": 1, "bytes": 0,
                    }
                    continue

                lib_state: dict[str, Any] = {
                    "status":            "running",
                    "pct":               0,
                    "files_transferred": 0,
                    "files_failed":      0,
                    "bytes":             0,
                }
                _active_run["libraries"][label] = lib_state
                manifest.log(run_id, "INFO", f"Scanning {label}: {source['path']}")

                try:
                    loop = asyncio.get_running_loop()
                    changed_files, skipped = await loop.run_in_executor(
                        executor,
                        lambda s=source, f=full: syncer.scan_source(s, force_full=f),  # type: ignore[misc]
                    )
                    with _run_mutex:
                        _active_run["files_skipped"] += skipped
                    total_files = len(changed_files)

                    if total_files == 0:
                        lib_state["status"] = "success"
                        lib_state["pct"]    = 100
                        manifest.log(run_id, "INFO",
                                     f"{label}: all files up-to-date, nothing to copy")
                        continue

                    manifest.log(run_id, "INFO",
                                 f"{label}: {total_files} files to copy, {skipped} skipped")

                    speed_window = {"bytes": 0, "ts": time.monotonic()}

                    def _progress_cb(chunk_bytes: int) -> None:
                        with _run_mutex:
                            speed_window["bytes"] += chunk_bytes
                            elapsed = time.monotonic() - speed_window["ts"]
                            if elapsed >= 1.0:
                                _active_run["speed_bps"] = int(
                                    speed_window["bytes"] / elapsed
                                )
                                speed_window["bytes"] = 0
                                speed_window["ts"]    = time.monotonic()

                    for f_idx, file_meta in enumerate(changed_files):
                        if _active_run.get("status") == "cancelled":
                            break

                        try:
                            backup_path = await loop.run_in_executor(
                                executor,
                                lambda fm=file_meta: syncer.copy_file(  # type: ignore[misc]
                                    fm, run_id, on_progress=_progress_cb
                                ),
                            )
                            manifest.record_file(
                                run_id, file_meta, backup_path,
                                key_fingerprint=syncer.key_fingerprint,
                            )
                            with _run_mutex:
                                lib_state["files_transferred"] += 1
                                lib_state["bytes"] += file_meta["size"]
                                _active_run["files_transferred"] += 1
                                _active_run["bytes_transferred"] += file_meta["size"]

                                feed_event = {
                                    "time":         datetime.now(timezone.utc).strftime("%H:%M:%S"),
                                    "file":         file_meta["name"],
                                    "size_mb":      round(file_meta["size"] / (1024 * 1024), 2),
                                    "library":      label,
                                    "checksum_ok":  True,
                                }
                                _active_run["feed"] = [feed_event] + _active_run["feed"][:49]

                        except Exception as file_err:
                            err_msg = str(file_err)
                            logger.error(
                                f"[{label}] File failed: {file_meta['name']} — {err_msg}"
                            )
                            with _run_mutex:
                                lib_state["files_failed"]      += 1
                                _active_run["files_failed"]    += 1
                                _active_run["errors"].append({
                                    "file":          file_meta["name"],
                                    "library":       label,
                                    "error":         err_msg,
                                    "original_path": file_meta.get("original_path"),
                                    "file_meta":     dict(file_meta),
                                })
                            manifest.log(run_id, "ERROR",
                                         f"{file_meta['name']}: {err_msg}")

                            fail_rate = lib_state["files_failed"] / max(total_files, 1)
                            threshold = cfg.circuit_breaker_threshold
                            if fail_rate > threshold and lib_state["files_failed"] >= 3:
                                logger.error(
                                    f"Circuit breaker tripped: {label} "
                                    f"({fail_rate:.0%} failure, threshold {threshold:.0%})"
                                )
                                lib_state["status"] = "circuit_broken"
                                await reporter.send_circuit_breaker_alert(
                                    library=label,
                                    fail_rate_pct=fail_rate * 100,
                                    run_id=run_id,
                                )
                                break

                        with _run_mutex:
                            lib_state["pct"] = round(
                                (f_idx + 1) / max(total_files, 1) * 100
                            )
                            _active_run["overall_pct"] = round(
                                ((idx + lib_state["pct"] / 100) / total_sources) * 100
                            )

                    # Flush batched manifest commits after each library
                    manifest.flush()

                    if lib_state["status"] not in ("circuit_broken", "failed", "cancelled"):
                        lib_state["status"] = (
                            "partial" if lib_state["files_failed"] > 0 else "success"
                        )

                except FileNotFoundError as src_err:
                    logger.error(f"[{label}] Source missing: {src_err}")
                    lib_state["status"] = "failed"
                    _active_run["errors"].append({"library": label, "error": str(src_err)})
                    manifest.log(run_id, "ERROR", f"{label}: {src_err}")

                except Exception as lib_err:
                    logger.error(f"[{label}] Library failed: {lib_err}")
                    lib_state["status"] = "failed"
                    _active_run["errors"].append({"library": label, "error": str(lib_err)})
                    manifest.log(run_id, "ERROR", f"{label}: {lib_err}")

        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        lib_statuses = [v["status"] for v in _active_run["libraries"].values()]
        if not lib_statuses or all(s == "success" for s in lib_statuses):
            final_status = "success"
        elif all(s in ("failed", "circuit_broken") for s in lib_statuses):
            final_status = "failed"
        else:
            final_status = "partial"

        with _run_mutex:
            # If the run was cancelled by the user, preserve that status —
            # do not overwrite it with success/partial from the post-cancel work.
            if _active_run.get("status") == "cancelled":
                final_status = "cancelled"
            _active_run["status"]      = final_status
            _active_run["overall_pct"] = 100
            _active_run["finished_at"] = datetime.now(timezone.utc).isoformat()

        manifest.finalize_run(run_id, _active_run)

        await _retry_locked_files(run_id, cfg=cfg, syncer=syncer, manifest=manifest)
        await _backup_manifest_to_ssd(cfg=cfg, manifest=manifest)
        await reporter.send_run_report(_active_run)

        logger.info(f"Run #{run_id} complete — {final_status}")

        if final_status == "success" and scheduler:
            scheduler.reset_missed_alert()

    except Exception as fatal_err:
        logger.error(f"Fatal backup error: {fatal_err}", exc_info=True)
        with _run_mutex:
            _active_run["status"]      = "failed"
            _active_run["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest.finalize_run(run_id, _active_run)
        await reporter.alert_and_notify(
            level="critical", title="GhostBackup fatal error",
            body=str(fatal_err), run_id=run_id, send_email=True,
        )


async def _retry_locked_files(
    run_id: int,
    cfg: Optional["ConfigManager"] = None,
    syncer: Optional["LocalSyncer"] = None,
    manifest: Optional["ManifestDB"] = None,
) -> None:
    """Attempt a second pass on files that failed due to locking."""
    cfg      = cfg      or _config
    syncer   = syncer   or _syncer
    manifest = manifest or _manifest
    assert cfg is not None and syncer is not None and manifest is not None
    assert _active_run is not None

    locked = [
        e for e in _active_run.get("errors", [])
        if "locked" in e.get("error", "").lower()
        or "permission" in e.get("error", "").lower()
    ]
    if not locked:
        return

    logger.info(f"Retrying {len(locked)} locked file(s)…")
    loop = asyncio.get_running_loop()

    for err_entry in locked:
        file_meta = dict(err_entry.get("file_meta") or {})
        src_path = err_entry.get("original_path") or file_meta.get("original_path") or err_entry.get("file", "")
        if not src_path:
            continue

        if not file_meta:
            label = err_entry.get("library", "")
            src = Path(src_path)
            if not src.exists():
                continue
            try:
                stat = src.stat()
                source_root = next(
                    (s["path"] for s in cfg.get_enabled_sources()
                     if s.get("label") == label),
                    str(src.parent),
                )
                file_meta = {
                    "source_label":  label,
                    "name":          src.name,
                    "original_path": str(src),
                    "rel_path":      str(src.relative_to(Path(source_root))),
                    "size":          stat.st_size,
                    "mtime":         stat.st_mtime,
                    "xxhash":        syncer.hash_file(src),
                }
            except Exception:
                continue

        try:
            backup_path = await loop.run_in_executor(
                None, lambda fm=file_meta: syncer.copy_file(fm, run_id)  # type: ignore[misc]
            )
            manifest.record_file(run_id, file_meta, backup_path)
            with _run_mutex:
                _active_run["files_transferred"] += 1
                _active_run["files_failed"] = max(_active_run["files_failed"] - 1, 0)
                err_entry["retried"] = True
                err_entry["retry_succeeded"] = True
            logger.info(f"Locked file retry succeeded: {file_meta.get('name', src_path)}")
        except Exception as retry_err:
            err_entry["retried"] = True
            err_entry["retry_error"] = str(retry_err)
            logger.warning(f"Locked file retry failed: {file_meta.get('name', src_path)} — {retry_err}")


async def _backup_manifest_to_ssd(
    cfg: Optional["ConfigManager"] = None,
    manifest: Optional["ManifestDB"] = None,
) -> None:
    """Copy the manifest database to the SSD after every successful run.

    Keeps the 3 most recent copies with timestamps to protect against
    corruption overwriting the only backup.
    """
    cfg      = cfg      or _config
    manifest = manifest or _manifest
    assert cfg is not None and manifest is not None
    if not cfg.ssd_path:
        return
    try:
        dest_dir = Path(cfg.ssd_path) / ".ghostbackup"
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Timestamped copy for rotation
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        db_dest = dest_dir / f"ghostbackup_{ts}.db"
        shutil.copy2(str(manifest.db_path), str(db_dest))
        # Also keep a latest symlink / copy for easy access
        latest = dest_dir / "ghostbackup.db"
        shutil.copy2(str(manifest.db_path), str(latest))
        # Prune old copies — keep only the 3 most recent
        backups = sorted(dest_dir.glob("ghostbackup_*.db"), reverse=True)
        for old in backups[3:]:
            old.unlink(missing_ok=True)
        logger.info(f"Manifest DB backed up to SSD: {db_dest} ({len(backups)} copies, kept 3)")
    except Exception as db_err:
        logger.warning(f"Manifest DB backup to SSD failed: {db_err}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health(cfg: ConfigManager = Depends(provide_config),
                 scheduler: BackupScheduler = Depends(get_scheduler),
                 syncer: LocalSyncer = Depends(get_syncer)):
    return {
        "status":            "ok",
        "version":           app.version,
        "scheduler_running": scheduler.is_running() if scheduler else False,
        "next_run":          scheduler.next_run_time() if scheduler else None,
        "schedule": {
            "time": cfg.schedule_time,
            "timezone": cfg.timezone,
            "label": f"Daily at {cfg.schedule_time} {cfg.timezone}",
        },
        "encryption_active": syncer.encryption_active if syncer else False,
        "hkdf_salt_active":  bool(cfg.hkdf_salt != b"ghostbackup-stream-v1"),
        "key_storage":       cfg.key_storage_method,
    }


@app.get("/health/deep")
@_limiter.limit("10/minute")
async def health_deep(request: Request,
                      cfg: ConfigManager = Depends(provide_config),
                      manifest: ManifestDB = Depends(get_manifest),
                      syncer: LocalSyncer = Depends(get_syncer),
                      scheduler: BackupScheduler = Depends(get_scheduler),
                      reporter: Reporter = Depends(get_reporter)):
    """
    Comprehensive health check for external monitoring.
    Returns SSD status, last backup age, encryption, integrity spot-check,
    scheduler state, drill status, and overall assessment.
    """
    from syncer import get_ssd_status

    # SSD
    ssd = get_ssd_status(cfg.ssd_path)
    ssd_connected = ssd.get("status") == "ok"
    ssd_free_gb = ssd.get("available_gb", 0)

    secondary_ssd = get_ssd_status(cfg.secondary_ssd_path) if cfg.secondary_ssd_path else None
    secondary_connected = secondary_ssd.get("status") == "ok" if secondary_ssd else None

    # Last backup
    last_run = manifest.get_latest_successful_run()
    last_age_hours = None
    last_status = None
    if last_run:
        last_dt = datetime.fromisoformat(last_run["started_at"])
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        last_age_hours = round(
            (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600, 1
        )
        last_status = last_run["status"]

    # Spot-check (up to 5 random files)
    spot = {"checked": 0, "passed": 0, "failed": 0}
    try:
        if last_run:
            all_files = manifest.get_files(last_run["id"])
            if all_files:
                sample = random.sample(all_files, min(5, len(all_files)))
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: syncer.verify_files(sample)
                )
                spot = {
                    "checked": result["verified"] + result["failed"] + result["missing"],
                    "passed": result["verified"],
                    "failed": result["failed"] + result["missing"],
                }
    except Exception as e:
        logger.warning(f"Deep health spot-check error: {e}")

    # Manifest
    manifest_ok = True
    manifest_size_mb: float = 0.0
    try:
        manifest_size_mb = round(manifest.db_path.stat().st_size / (1024 * 1024), 1)
    except Exception:
        manifest_ok = False

    # Restore drill
    drill_last = manifest.get_last_drill_completion()
    drill_overdue = False
    drill_days_remaining = None
    if drill_last:
        drill_dt = datetime.fromisoformat(drill_last)
        if drill_dt.tzinfo is None:
            drill_dt = drill_dt.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - drill_dt).days
        drill_overdue = days_since >= 30
        drill_days_remaining = max(0, 30 - days_since)

    # Overall assessment
    overall = "healthy"
    if not ssd_connected or not syncer.encryption_active or spot["failed"] > 0:
        overall = "unhealthy"
    elif (last_age_hours and last_age_hours > 36) or drill_overdue or \
         (secondary_connected is False):
        overall = "degraded"

    return {
        "ssd_connected":               ssd_connected,
        "ssd_free_gb":                 ssd_free_gb,
        "secondary_ssd_connected":     secondary_connected,
        "last_backup_age_hours":       last_age_hours,
        "last_backup_status":          last_status,
        "encryption_active":           syncer.encryption_active if syncer else False,
        "key_storage":                 cfg.key_storage_method,
        "manifest_ok":                 manifest_ok,
        "manifest_size_mb":            manifest_size_mb,
        "spot_check":                  spot,
        "scheduler_running":           scheduler.is_running() if scheduler else False,
        "next_backup":                 scheduler.next_run_time() if scheduler else None,
        "restore_drill_overdue":       drill_overdue,
        "restore_drill_days_remaining": drill_days_remaining,
        "version":                     app.version,
        "overall":                     overall,
    }


@app.get("/ssd/status")
async def ssd_status(cfg: ConfigManager = Depends(provide_config)):
    return get_ssd_status(cfg.ssd_path)


@app.get("/dashboard")
async def dashboard(cfg: ConfigManager = Depends(provide_config),
                    manifest: ManifestDB = Depends(get_manifest),
                    scheduler: BackupScheduler = Depends(get_scheduler)):
    runs = manifest.get_runs(limit=30)
    last = runs[0] if runs else None
    ssd  = get_ssd_status(cfg.ssd_path)
    return {
        "runs":        runs,
        "last_run":    last,
        "ssd_storage": ssd,
        "next_run":    scheduler.next_run_time() if scheduler else None,
        "schedule": {
            "time": cfg.schedule_time,
            "timezone": cfg.timezone,
            "label": f"Daily at {cfg.schedule_time} {cfg.timezone}",
        },
        "active_run":  dict(_active_run) if _active_run else None,
    }


@app.post("/run/start")
@_limiter.limit("10/minute")
async def start_run(request: Request, req: RunRequest, background_tasks: BackgroundTasks,
                    cfg: ConfigManager = Depends(provide_config),
                    manifest: ManifestDB = Depends(get_manifest),
                    reporter: Reporter = Depends(get_reporter),
                    syncer: LocalSyncer = Depends(get_syncer),
                    scheduler: BackupScheduler = Depends(get_scheduler)):
    with _run_mutex:
        if _active_run and _active_run.get("status") == "running":
            raise_gb("GB-E020", 409)
    background_tasks.add_task(
        run_backup_job, req.full, req.sources,
        cfg, manifest, reporter, syncer, scheduler,
    )
    return {"message": "Backup job started", "full": req.full}


@app.post("/run/stop")
async def stop_run():
    with _run_mutex:
        if not _active_run or _active_run.get("status") != "running":
            raise HTTPException(400, "No active run to stop")
        _active_run["status"]      = "cancelled"
        _active_run["finished_at"] = datetime.now(timezone.utc).isoformat()
    return {"message": "Run cancellation requested"}


@app.get("/run/status")
async def run_status():
    with _run_mutex:
        if not _active_run:
            return {"status": "idle"}
        return dict(_active_run)


@app.get("/runs")
async def get_runs(limit: int = Query(default=30, ge=1, le=1000), offset: int = Query(default=0, ge=0),
                   manifest: ManifestDB = Depends(get_manifest)):
    return manifest.get_runs(limit=limit, offset=offset)


@app.get("/runs/{run_id}")
async def get_run(run_id: int, manifest: ManifestDB = Depends(get_manifest)):
    run = manifest.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run #{run_id} not found")
    return run


@app.get("/runs/export")
async def export_runs_csv(limit: int = Query(default=1000, ge=1, le=10000),
                          manifest: ManifestDB = Depends(get_manifest)):
    runs = manifest.get_runs(limit=limit, offset=0)
    buf = io.StringIO()
    fields = ["run_id", "started_at", "finished_at", "status", "files_transferred",
              "files_failed", "files_skipped", "bytes_transferred", "duration_seconds"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in runs:
        writer.writerow({k: r.get(k, "") for k in fields})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ghostbackup_runs.csv"},
    )


@app.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: int, level: str = "ALL",
                       manifest: ManifestDB = Depends(get_manifest)):
    return manifest.get_logs(run_id, level=level if level != "ALL" else None)


@app.get("/runs/{run_id}/files")
async def get_run_files(run_id: int, library: Optional[str] = None,
                        manifest: ManifestDB = Depends(get_manifest)):
    return manifest.get_files(run_id, library=library)


@app.get("/config")
async def get_config(cfg: ConfigManager = Depends(provide_config)):
    return cfg.to_dict_safe()


@app.patch("/config")
async def update_config(req: ConfigUpdateRequest,
                        cfg: ConfigManager = Depends(provide_config),
                        scheduler: BackupScheduler = Depends(get_scheduler),
                        watcher: FileWatcher = Depends(get_watcher)):
    updates         = req.model_dump(exclude_none=True)
    watcher_enabled = updates.pop("watcher_enabled", None)
    ignored         = cfg.update(updates)
    if "schedule_time" in updates or "timezone" in updates:
        scheduler.reschedule(cfg.schedule_time, cfg.timezone)
    global _syncer
    assert _manifest is not None
    _syncer = LocalSyncer(cfg, _manifest)
    if watcher_enabled is True and watcher and not watcher.is_running:
        watcher.reload_sources()
    elif watcher_enabled is False and watcher and watcher.is_running:
        watcher.stop()
    response = {"message": "Config updated", "config": cfg.to_dict_safe()}
    if ignored:
        response["ignored_keys"] = ignored
    return response


@app.post("/config/sites")
async def add_site(req: SiteRequest,
                   cfg: ConfigManager = Depends(provide_config),
                   watcher: FileWatcher = Depends(get_watcher)):
    source = cfg.add_site(req.model_dump(exclude_none=True))
    if watcher:
        watcher.reload_sources()
    return {"message": "Source added", "source": source, "config": cfg.to_dict_safe()}


@app.post("/config/reset")
async def reset_config(cfg: ConfigManager = Depends(provide_config),
                       scheduler: BackupScheduler = Depends(get_scheduler),
                       watcher: FileWatcher = Depends(get_watcher)):
    """Reset all configuration to factory defaults."""
    if not cfg:
        raise HTTPException(500, "Config not initialised")
    cfg.reset_to_defaults()
    if scheduler:
        scheduler.reschedule(cfg.schedule_time, cfg.timezone)
    if watcher and watcher.is_running:
        watcher.stop()
    return {"message": "Configuration reset to defaults", "config": cfg.to_dict_safe()}


@app.patch("/config/sites/{site_name}")
async def update_site(site_name: str, req: SiteUpdateRequest,
                      cfg: ConfigManager = Depends(provide_config),
                      watcher: FileWatcher = Depends(get_watcher)):
    try:
        source = cfg.update_site(site_name, req.model_dump(exclude_none=True))
    except ValueError:
        raise HTTPException(404, f"Source '{site_name}' not found")
    if watcher:
        watcher.reload_sources()
    return {"message": "Source updated", "source": source}


@app.delete("/config/sites/{site_name}")
async def remove_site(site_name: str,
                      cfg: ConfigManager = Depends(provide_config),
                      watcher: FileWatcher = Depends(get_watcher)):
    removed = cfg.remove_site(site_name)
    if not removed:
        raise HTTPException(404, f"Source '{site_name}' not found")
    if watcher:
        watcher.reload_sources()
    return {"message": "Source removed", "config": cfg.to_dict_safe()}


@app.get("/config/audit")
async def get_config_audit(limit: int = Query(default=100, ge=1, le=1000),
                           manifest: ManifestDB = Depends(get_manifest)):
    return manifest.get_config_audit(limit=limit)


@app.post("/restore")
@_limiter.limit("5/minute")
async def restore(request: Request, req: RestoreRequest, background_tasks: BackgroundTasks,
                  manifest: ManifestDB = Depends(get_manifest), syncer: LocalSyncer = Depends(get_syncer)):
    run = manifest.get_run(req.run_id)
    if not run:
        raise HTTPException(404, f"Run #{req.run_id} not found")
    if run["status"] == "failed":
        raise_gb("GB-E040")

    files = manifest.get_files(req.run_id, library=req.library,
                               subfolder=req.subfolder)
    if not files:
        raise_gb("GB-E041", 404)

    # Validate destination path to prevent path traversal
    dest_resolved = Path(req.destination).resolve()
    if ".." in dest_resolved.parts:
        raise_gb("GB-E042")

    if req.dry_run:
        return {
            "dry_run":          True,
            "files_to_restore": len(files),
            "destination":      req.destination,
            "files": [
                {"name": f["name"], "size": f.get("size", 0),
                 "path": f["backup_path"]}
                for f in files
            ],
        }

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: syncer.restore_files(files, req.destination)
        )
        manifest.record_drill(
            restore_run_id=req.run_id,
            notes=f"Restore of run #{req.run_id} to {req.destination}",
        )
        return {
            "dry_run":      False,
            "message":      (
                f"Restore complete — {result.get('restored', 0)} files "
                f"written to {req.destination}"
            ),
            "files_count":  result.get("restored", 0),
            "files_failed": result.get("failed", 0),
            "destination":  req.destination,
            "errors":       result.get("errors", []),
        }
    except Exception as e:
        raise HTTPException(500, f"Restore failed: {e}")


@app.post("/verify")
@_limiter.limit("5/minute")
async def verify_backups(request: Request,
                         source_label: Optional[str] = None,
                         syncer: Optional[LocalSyncer] = Depends(get_syncer)):
    """
    Re-reads backed-up files and verifies hashes against the manifest.
    Run manually or schedule weekly to catch SSD corruption early.
    Returns results synchronously so the UI can display them.
    """
    if _active_run and _active_run.get("status") == "running":
        raise_gb("GB-E060", 409)

    active_syncer = syncer or _syncer
    assert active_syncer is not None
    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: active_syncer.verify_backups(source_label),
    )
    alert_level: Any = "error" if (result["failed"] or result["missing"]) else "info"
    assert _reporter is not None
    _reporter.alerts.add(
        alert_level,
        "Backup verification complete",
        f"{result['verified']} OK, {result['failed']} corrupt, {result['missing']} missing.",
    )
    if result["failed"] or result["missing"]:
        await _reporter.alert_and_notify(
            level="error",
            title="Backup integrity issue detected",
            body=(
                f"{result['failed']} file(s) have hash mismatches and may be corrupt. "
                f"{result['missing']} file(s) are missing from SSD. "
                "Run a full backup immediately."
            ),
            send_email=True,
        )
    logger.info(f"Verification done — {result}")
    return {
        "verified": result["verified"],
        "failed":   result["failed"],
        "missing":  result["missing"],
        "source":   source_label or "all",
    }


@app.patch("/settings/smtp")
async def update_smtp(req: SmtpUpdateRequest,
                      cfg: ConfigManager = Depends(provide_config)):
    cfg.update_smtp(req.model_dump(exclude_none=True))
    return {"message": "SMTP settings updated"}


@app.post("/settings/smtp/test")
@_limiter.limit("3/minute")
async def test_smtp(request: Request, reporter: Reporter = Depends(get_reporter)):
    try:
        await reporter.send_test_email()
        return {"message": "Test email sent successfully"}
    except Exception as e:
        raise_gb("GB-E050", 500, f"SMTP test failed: {e}")


@app.patch("/settings/retention")
async def update_retention(req: RetentionUpdateRequest,
                           cfg: ConfigManager = Depends(provide_config)):
    try:
        cfg.update_retention(req.model_dump())
        return {"message": "Retention policy updated"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/settings/prune")
async def run_prune(background_tasks: BackgroundTasks,
                    cfg: ConfigManager = Depends(provide_config),
                    syncer: LocalSyncer = Depends(get_syncer),
                    reporter: Reporter = Depends(get_reporter)):
    if _active_run and _active_run.get("status") == "running":
        raise_gb("GB-E061", 409)
    background_tasks.add_task(_do_prune, cfg, syncer, reporter)
    return {"message": "Prune job started"}


async def _do_prune(cfg: ConfigManager, syncer: LocalSyncer, reporter: Reporter):
    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: syncer.prune_old_backups(
            cfg.retention_daily_days,
            cfg.retention_weekly_days,
            cfg.retention_guard_days,
        ),
    )
    removed = result["removed"]
    skipped = result["immutable_skipped"]
    logger.info(f"Prune complete — {removed} files removed, {skipped} immutable skipped")
    reporter.alerts.add(
        "info", "Prune complete",
        f"{removed} old backup files removed from SSD."
        + (f" {skipped} recent backups protected by immutability window." if skipped else ""),
    )


@app.post("/settings/encryption/generate-key")
@_limiter.limit("5/minute")
async def generate_encryption_key(request: Request, cfg: ConfigManager = Depends(provide_config)):
    """
    Generate a new Fernet encryption key and return it to the UI.
    The key is NOT stored anywhere by the backend — the user must
    copy it into .env.local manually before restarting GhostBackup.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise HTTPException(500, "cryptography package not installed")
    return {"key": Fernet.generate_key().decode()}


@app.get("/watcher/status")
async def watcher_status(watcher: FileWatcher = Depends(get_watcher)):
    if not watcher:
        return {"running": False, "sources": [], "error": "Watcher not initialised"}
    return watcher.status()


@app.post("/watcher/start")
async def watcher_start(cfg: ConfigManager = Depends(provide_config),
                        watcher: FileWatcher = Depends(get_watcher)):
    if not watcher:
        raise HTTPException(503, "Watcher not initialised")
    if watcher.is_running:
        return {"message": "Watcher already running", **watcher.status()}
    if not cfg.get_enabled_sources():
        raise HTTPException(
            400, "No enabled source folders — add at least one source first"
        )
    watcher.reload_sources()
    return {"message": "Watcher started", **watcher.status()}


@app.post("/watcher/stop")
async def watcher_stop(watcher: FileWatcher = Depends(get_watcher)):
    if not watcher:
        raise HTTPException(503, "Watcher not initialised")
    if not watcher.is_running:
        return {"message": "Watcher is not running"}
    watcher.stop()
    return {"message": "Watcher stopped"}


@app.get("/alerts")
async def get_alerts(include_dismissed: bool = False,
                     reporter: Reporter = Depends(get_reporter)):
    return {
        "alerts":       reporter.alerts.get_all(include_dismissed=include_dismissed),
        "unread_count": reporter.alerts.unread_count(),
    }


@app.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: int, reporter: Reporter = Depends(get_reporter)):
    ok = reporter.alerts.dismiss(alert_id)
    if not ok:
        raise HTTPException(404, f"Alert #{alert_id} not found")
    return {"dismissed": alert_id, "unread_count": reporter.alerts.unread_count()}


@app.post("/alerts/dismiss-all")
async def dismiss_all_alerts(reporter: Reporter = Depends(get_reporter)):
    count = reporter.alerts.dismiss_all()
    return {"dismissed": count, "unread_count": 0}


@app.get("/settings/drill-status")
async def drill_status(manifest: ManifestDB = Depends(get_manifest)):
    last = manifest.get_last_drill_completion()
    history = manifest.get_drill_history(limit=12)
    days_since = None
    next_due = None
    if last:
        from datetime import timedelta
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last_dt).days
        next_due = (last_dt + timedelta(days=30)).isoformat()
    return {
        "last_completed": last,
        "days_since_last": days_since,
        "next_due": next_due,
        "overdue": days_since is not None and days_since >= 30,
        "history": history,
    }


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=int(os.getenv("GHOSTBACKUP_API_PORT", "8765")),
        log_level="info",
        reload=False,
    )
