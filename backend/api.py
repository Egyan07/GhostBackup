"""
api.py — GhostBackup FastAPI Local IPC Server

Runs on http://127.0.0.1:<GHOSTBACKUP_API_PORT> and is spawned by the Electron
main process. All endpoints except /health require an X-API-Key header
matching the token injected via the GHOSTBACKUP_API_TOKEN environment
variable at startup.
"""

import asyncio
import hmac
import http.client
import json
import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
from reporter import Reporter
from scheduler import BackupScheduler
from syncer import LocalSyncer, get_ssd_status
from watcher import FileWatcher

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
_active_run:      Optional[dict]            = None
_active_run_lock: Optional[asyncio.Lock]    = None
_run_mutex:       threading.Lock            = threading.Lock()  # protects _active_run mutations from thread pool

# ── Rate limiter ──────────────────────────────────────────────────────────────
_limiter = Limiter(key_func=get_remote_address)


# ── Dependency providers ──────────────────────────────────────────────────────

def get_config() -> ConfigManager:
    return _config


def get_manifest() -> ManifestDB:
    return _manifest


def get_scheduler() -> BackupScheduler:
    return _scheduler


def get_reporter() -> Reporter:
    return _reporter


def get_syncer() -> LocalSyncer:
    return _syncer


def get_watcher() -> FileWatcher:
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
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _manifest, _scheduler, _reporter, _syncer, _watcher, _active_run_lock

    _active_run_lock = asyncio.Lock()
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

    if _syncer._crypto.enabled:
        logger.info("Backup encryption: ACTIVE")
    else:
        logger.warning(
            "Backup encryption: INACTIVE — set GHOSTBACKUP_ENCRYPTION_KEY to enable"
        )

    logger.info(f"GhostBackup API ready on http://127.0.0.1:{API_PORT}")
    yield

    logger.info("GhostBackup API shutting down…")
    if _watcher and _watcher._running:
        _watcher.stop()
    if _scheduler:
        _scheduler.stop()
    if _manifest:
        _manifest.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="GhostBackup API", version="2.4.0", lifespan=lifespan)

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

async def run_backup_job(full: bool = False, sources: list[str] = None) -> None:
    global _active_run

    async with _active_run_lock:
        if _active_run and _active_run.get("status") == "running":
            logger.warning("Backup already running — skipping duplicate trigger")
            return

        ssd_status = _syncer.check_ssd()
        if ssd_status["status"] != "ok":
            err = ssd_status.get("error", "SSD unavailable")
            logger.error(f"Backup aborted — {err}")
            await _reporter.alert_and_notify(
                level="error", title="Backup aborted — SSD unavailable",
                body=err, send_email=True,
            )
            return

        run_id      = _manifest.create_run(full_backup=full)
        _active_run = _new_run_state(run_id, full)

    if _scheduler:
        _scheduler.set_current_run_id(run_id)

    try:
        target_sources = [
            s for s in _config.get_enabled_sources()
            if not sources or (s.get("label") or s.get("name", "")) in sources
        ]

        if not target_sources:
            raise RuntimeError("No enabled source folders configured")

        total_sources = len(target_sources)
        executor      = ThreadPoolExecutor(max_workers=_config.concurrency)

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

                lib_state = {
                    "status":            "running",
                    "pct":               0,
                    "files_transferred": 0,
                    "files_failed":      0,
                    "bytes":             0,
                }
                _active_run["libraries"][label] = lib_state
                _manifest.log(run_id, "INFO", f"Scanning {label}: {source['path']}")

                try:
                    loop = asyncio.get_running_loop()
                    changed_files, skipped = await loop.run_in_executor(
                        executor,
                        lambda s=source, f=full: _syncer.scan_source(s, force_full=f),
                    )
                    with _run_mutex:
                        _active_run["files_skipped"] += skipped
                    total_files = len(changed_files)

                    if total_files == 0:
                        lib_state["status"] = "success"
                        lib_state["pct"]    = 100
                        _manifest.log(run_id, "INFO",
                                      f"{label}: all files up-to-date, nothing to copy")
                        continue

                    _manifest.log(run_id, "INFO",
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
                                lambda fm=file_meta: _syncer.copy_file(
                                    fm, run_id, on_progress=_progress_cb
                                ),
                            )
                            _manifest.record_file(run_id, file_meta, backup_path)
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
                            _manifest.log(run_id, "ERROR",
                                          f"{file_meta['name']}: {err_msg}")

                            fail_rate = lib_state["files_failed"] / max(total_files, 1)
                            threshold = _config.circuit_breaker_threshold
                            if fail_rate > threshold and lib_state["files_failed"] >= 3:
                                logger.error(
                                    f"Circuit breaker tripped: {label} "
                                    f"({fail_rate:.0%} failure, threshold {threshold:.0%})"
                                )
                                lib_state["status"] = "circuit_broken"
                                await _reporter.send_circuit_breaker_alert(
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
                    _manifest.flush()

                    if lib_state["status"] not in ("circuit_broken", "failed", "cancelled"):
                        lib_state["status"] = (
                            "partial" if lib_state["files_failed"] > 0 else "success"
                        )

                except FileNotFoundError as src_err:
                    logger.error(f"[{label}] Source missing: {src_err}")
                    lib_state["status"] = "failed"
                    _active_run["errors"].append({"library": label, "error": str(src_err)})
                    _manifest.log(run_id, "ERROR", f"{label}: {src_err}")

                except Exception as lib_err:
                    logger.error(f"[{label}] Library failed: {lib_err}")
                    lib_state["status"] = "failed"
                    _active_run["errors"].append({"library": label, "error": str(lib_err)})
                    _manifest.log(run_id, "ERROR", f"{label}: {lib_err}")

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

        _manifest.finalize_run(run_id, _active_run)

        await _retry_locked_files(run_id)
        await _backup_manifest_to_ssd()
        await _reporter.send_run_report(_active_run)

        logger.info(f"Run #{run_id} complete — {final_status}")

        if final_status == "success" and _scheduler:
            _scheduler._missed_alerted = False

    except Exception as fatal_err:
        logger.error(f"Fatal backup error: {fatal_err}", exc_info=True)
        with _run_mutex:
            _active_run["status"]      = "failed"
            _active_run["finished_at"] = datetime.now(timezone.utc).isoformat()
        _manifest.finalize_run(run_id, _active_run)
        await _reporter.alert_and_notify(
            level="critical", title="GhostBackup fatal error",
            body=str(fatal_err), run_id=run_id, send_email=True,
        )


async def _retry_locked_files(run_id: int) -> None:
    """Attempt a second pass on files that failed due to locking."""
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
                    (s["path"] for s in _config.get_enabled_sources()
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
                    "xxhash":        _syncer.hash_file(src),
                }
            except Exception:
                continue

        try:
            backup_path = await loop.run_in_executor(
                None, lambda fm=file_meta: _syncer.copy_file(fm, run_id)
            )
            _manifest.record_file(run_id, file_meta, backup_path)
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


async def _backup_manifest_to_ssd() -> None:
    """Copy the manifest database to the SSD after every successful run."""
    if not _config.ssd_path:
        return
    try:
        db_dest = Path(_config.ssd_path) / ".ghostbackup" / "ghostbackup.db"
        db_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_manifest._path), str(db_dest))
        logger.info(f"Manifest DB backed up to SSD: {db_dest}")
    except Exception as db_err:
        logger.warning(f"Manifest DB backup to SSD failed: {db_err}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":            "ok",
        "version":           "2.3.2",
        "scheduler_running": _scheduler.is_running() if _scheduler else False,
        "next_run":          _scheduler.next_run_time() if _scheduler else None,
        "schedule": {
            "time": _config.schedule_time,
            "timezone": _config.timezone,
            "label": f"Daily at {_config.schedule_time} {_config.timezone}",
        },
        "encryption_active": _syncer._crypto.enabled if _syncer else False,
    }


@app.get("/ssd/status")
async def ssd_status():
    return get_ssd_status(_config.ssd_path)


@app.get("/dashboard")
async def dashboard():
    runs = _manifest.get_runs(limit=30)
    last = runs[0] if runs else None
    ssd  = get_ssd_status(_config.ssd_path)
    return {
        "runs":        runs,
        "last_run":    last,
        "ssd_storage": ssd,
        "next_run":    _scheduler.next_run_time() if _scheduler else None,
        "schedule": {
            "time": _config.schedule_time,
            "timezone": _config.timezone,
            "label": f"Daily at {_config.schedule_time} {_config.timezone}",
        },
        "active_run":  _active_run,
    }


@app.post("/run/start")
@_limiter.limit("10/minute")
async def start_run(request: Request, req: RunRequest, background_tasks: BackgroundTasks,
                    cfg: ConfigManager = Depends(get_config)):
    with _run_mutex:
        if _active_run and _active_run.get("status") == "running":
            raise HTTPException(409, "A backup run is already in progress")
    background_tasks.add_task(run_backup_job, req.full, req.sources)
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
    if not _active_run:
        return {"status": "idle"}
    return _active_run


@app.get("/runs")
async def get_runs(limit: int = Query(default=30, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    return _manifest.get_runs(limit=limit, offset=offset)


@app.get("/runs/{run_id}")
async def get_run(run_id: int):
    run = _manifest.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run #{run_id} not found")
    return run


@app.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: int, level: str = "ALL"):
    return _manifest.get_logs(run_id, level=level if level != "ALL" else None)


@app.get("/runs/{run_id}/files")
async def get_run_files(run_id: int, library: Optional[str] = None):
    return _manifest.get_files(run_id, library=library)


@app.get("/config")
async def get_config():
    return _config.to_dict_safe()


@app.patch("/config")
async def update_config(req: ConfigUpdateRequest):
    updates        = req.model_dump(exclude_none=True)
    watcher_enabled = updates.pop("watcher_enabled", None)
    _config.update(updates)
    if "schedule_time" in updates or "timezone" in updates:
        _scheduler.reschedule(_config.schedule_time, _config.timezone)
    global _syncer
    _syncer = LocalSyncer(_config, _manifest)
    if watcher_enabled is True and _watcher and not _watcher._running:
        _watcher.reload_sources()
    elif watcher_enabled is False and _watcher and _watcher._running:
        _watcher.stop()
    return {"message": "Config updated", "config": _config.to_dict_safe()}


@app.post("/config/sites")
async def add_site(req: SiteRequest):
    source = _config.add_site(req.model_dump(exclude_none=True))
    if _watcher:
        _watcher.reload_sources()
    return {"message": "Source added", "source": source, "config": _config.to_dict_safe()}


@app.post("/config/reset")
async def reset_config():
    """Reset all configuration to factory defaults."""
    if not _config:
        raise HTTPException(500, "Config not initialised")
    _config.reset_to_defaults()
    if _scheduler:
        _scheduler.reschedule(_config.schedule_time, _config.timezone)
    if _watcher and _watcher._running:
        _watcher.stop()
    return {"message": "Configuration reset to defaults", "config": _config.to_dict_safe()}


@app.patch("/config/sites/{site_name}")
async def update_site(site_name: str, req: SiteUpdateRequest):
    try:
        source = _config.update_site(site_name, req.model_dump(exclude_none=True))
    except ValueError:
        raise HTTPException(404, f"Source '{site_name}' not found")
    if _watcher:
        _watcher.reload_sources()
    return {"message": "Source updated", "source": source}


@app.delete("/config/sites/{site_name}")
async def remove_site(site_name: str):
    removed = _config.remove_site(site_name)
    if not removed:
        raise HTTPException(404, f"Source '{site_name}' not found")
    if _watcher:
        _watcher.reload_sources()
    return {"message": "Source removed", "config": _config.to_dict_safe()}


@app.get("/config/audit")
async def get_config_audit(limit: int = Query(default=100, ge=1, le=1000)):
    return _manifest.get_config_audit(limit=limit)


@app.post("/restore")
@_limiter.limit("5/minute")
async def restore(request: Request, req: RestoreRequest, background_tasks: BackgroundTasks,
                  manifest: ManifestDB = Depends(get_manifest), syncer: LocalSyncer = Depends(get_syncer)):
    run = _manifest.get_run(req.run_id)
    if not run:
        raise HTTPException(404, f"Run #{req.run_id} not found")
    if run["status"] == "failed":
        raise HTTPException(400, "Cannot restore from a failed run")

    files = _manifest.get_files(req.run_id, library=req.library,
                                subfolder=req.subfolder)
    if not files:
        raise HTTPException(404, "No files found matching the restore criteria")

    # Validate destination path to prevent path traversal
    dest_resolved = Path(req.destination).resolve()
    if ".." in dest_resolved.parts:
        raise HTTPException(400, "Path traversal detected in destination")

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
            None, lambda: _syncer.restore_files(files, req.destination)
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
async def verify_backups(request: Request, background_tasks: BackgroundTasks,
                         source_label: Optional[str] = None,
                         syncer: LocalSyncer = Depends(get_syncer)):
    """
    Re-reads backed-up files and verifies hashes against the manifest.
    Run manually or schedule weekly to catch SSD corruption early.
    """
    if _active_run and _active_run.get("status") == "running":
        raise HTTPException(409, "Cannot verify while a backup is running")
    background_tasks.add_task(_do_verify, source_label)
    return {"message": "Verification started", "source": source_label or "all"}


async def _do_verify(source_label: Optional[str] = None):
    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _syncer.verify_backups(source_label),
    )
    level = "error" if (result["failed"] or result["missing"]) else "info"
    _reporter.alerts.add(
        level,
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


@app.patch("/settings/smtp")
async def update_smtp(req: SmtpUpdateRequest):
    _config.update_smtp(req.model_dump(exclude_none=True))
    return {"message": "SMTP settings updated"}


@app.post("/settings/smtp/test")
@_limiter.limit("3/minute")
async def test_smtp(request: Request, reporter: Reporter = Depends(get_reporter)):
    try:
        await _reporter.send_test_email()
        return {"message": "Test email sent successfully"}
    except Exception as e:
        raise HTTPException(500, f"SMTP test failed: {e}")


@app.patch("/settings/retention")
async def update_retention(req: RetentionUpdateRequest):
    try:
        _config.update_retention(req.model_dump())
        return {"message": "Retention policy updated"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/settings/prune")
async def run_prune(background_tasks: BackgroundTasks):
    if _active_run and _active_run.get("status") == "running":
        raise HTTPException(409, "Cannot prune while a backup is running")
    background_tasks.add_task(_do_prune)
    return {"message": "Prune job started"}


async def _do_prune():
    loop   = asyncio.get_running_loop()
    pruned = await loop.run_in_executor(
        None,
        lambda: _syncer.prune_old_backups(
            _config.retention_daily_days,
            _config.retention_weekly_days,
            _config.retention_guard_days,
        ),
    )
    logger.info(f"Prune complete — {pruned} files removed")
    _reporter.alerts.add(
        "info", "Prune complete",
        f"{pruned} old backup files removed from SSD.",
    )


@app.post("/settings/encryption/generate-key")
@_limiter.limit("5/minute")
async def generate_encryption_key(request: Request, cfg: ConfigManager = Depends(get_config)):
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
async def watcher_status():
    if not _watcher:
        return {"running": False, "sources": [], "error": "Watcher not initialised"}
    return _watcher.status()


@app.post("/watcher/start")
async def watcher_start():
    if not _watcher:
        raise HTTPException(503, "Watcher not initialised")
    if _watcher._running:
        return {"message": "Watcher already running", **_watcher.status()}
    if not _config.get_enabled_sources():
        raise HTTPException(
            400, "No enabled source folders — add at least one source first"
        )
    _watcher.reload_sources()
    return {"message": "Watcher started", **_watcher.status()}


@app.post("/watcher/stop")
async def watcher_stop():
    if not _watcher:
        raise HTTPException(503, "Watcher not initialised")
    if not _watcher._running:
        return {"message": "Watcher is not running"}
    _watcher.stop()
    return {"message": "Watcher stopped"}


@app.get("/alerts")
async def get_alerts(include_dismissed: bool = False):
    return {
        "alerts":       _reporter.alerts.get_all(include_dismissed=include_dismissed),
        "unread_count": _reporter.alerts.unread_count(),
    }


@app.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: int):
    ok = _reporter.alerts.dismiss(alert_id)
    if not ok:
        raise HTTPException(404, f"Alert #{alert_id} not found")
    return {"dismissed": alert_id, "unread_count": _reporter.alerts.unread_count()}


@app.post("/alerts/dismiss-all")
async def dismiss_all_alerts():
    count = _reporter.alerts.dismiss_all()
    return {"dismissed": count, "unread_count": 0}


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=int(os.getenv("GHOSTBACKUP_API_PORT", "8765")),
        log_level="info",
        reload=False,
    )
