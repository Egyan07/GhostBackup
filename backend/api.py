"""
api.py — GhostBackup FastAPI Local IPC Server  (Phase 3: Real-Time Watcher)

Phase 3 additions:
  - watcher.py (FileWatcher) initialised in lifespan — watches all source folders
  - /watcher/status  GET  — returns running state + per-source pending/last-trigger info
  - /watcher/start   POST — enable real-time watching (persisted in config)
  - /watcher/stop    POST — disable real-time watching
  - /config/sites POST + DELETE now call watcher.reload_sources() automatically
  - ConfigUpdateRequest.watcher_enabled added

Phase 2: Local SSD engine (syncer.py, no cloud APIs).
Phase 1: Auto-start, port kill, tray icon (electron/main.js).
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import ConfigManager
from manifest import ManifestDB
from reporter import Reporter
from scheduler import BackupScheduler
from syncer import LocalSyncer, get_ssd_status
from watcher import FileWatcher

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api")

# ── Global state ──────────────────────────────────────────────────────────────
_config:     Optional[ConfigManager]   = None
_manifest:   Optional[ManifestDB]      = None
_scheduler:  Optional[BackupScheduler] = None
_reporter:   Optional[Reporter]        = None
_syncer:     Optional[LocalSyncer]     = None
_watcher:    Optional[FileWatcher]     = None
_active_run: Optional[dict]            = None


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _manifest, _scheduler, _reporter, _syncer, _watcher

    logger.info("GhostBackup API starting…")

    _config   = ConfigManager()
    _manifest = ManifestDB()
    _reporter = Reporter(_config)
    _syncer   = LocalSyncer(_config, _manifest)
    _scheduler = BackupScheduler(_config, run_backup_job, reporter=_reporter)

    # Phase 2: desktop notify callback
    async def _desktop_notify(title: str, body: str) -> None:
        import http.client, json
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 8766, timeout=2)
            conn.request("POST", "/notify",
                         body=json.dumps({"title": title, "body": body}),
                         headers={"Content-Type": "application/json"})
            conn.getresponse()
            conn.close()
        except Exception:
            pass

    _reporter.set_notify_callback(_desktop_notify)
    _scheduler.set_manifest(_manifest)
    _scheduler.start()

    # Phase 3: real-time file watcher — auto-starts if sources are configured
    _watcher = FileWatcher(_config, run_backup_job, asyncio.get_event_loop())
    if _config.get_enabled_sources():
        try:
            _watcher.start()
        except Exception as e:
            logger.warning(f"FileWatcher failed to start: {e}")

    logger.info("GhostBackup API ready on http://127.0.0.1:8765")
    yield

    logger.info("GhostBackup API shutting down…")
    if _watcher and _watcher._running:
        _watcher.stop()
    if _scheduler:
        _scheduler.stop()
    if _manifest:
        _manifest.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="GhostBackup API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "file://"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    full:    bool      = False
    sources: list[str] = []     # empty = all enabled sources


class RestoreRequest(BaseModel):
    run_id:      int
    library:     str              # source_label (UI sends 'library' key)
    subfolder:   Optional[str] = None
    destination: str
    dry_run:     bool = True


class ConfigUpdateRequest(BaseModel):
    ssd_path:         Optional[str]       = None
    schedule_time:    Optional[str]       = None
    timezone:         Optional[str]       = None
    concurrency:      Optional[int]       = None
    max_file_size_gb: Optional[int]       = None
    verify_checksums: Optional[bool]      = None
    version_count:    Optional[int]       = None
    exclude_patterns: Optional[list[str]] = None
    watcher_enabled:  Optional[bool]      = None   # Phase 3


class SiteRequest(BaseModel):
    """UI sends this for both add-source and legacy sites."""
    label:   Optional[str] = None
    name:    Optional[str] = None     # fallback if UI sends 'name'
    path:    str
    enabled: bool = True


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


# ── Core backup job ───────────────────────────────────────────────────────────

async def run_backup_job(full: bool = False, sources: list[str] = None) -> None:
    """
    Core backup job — runs as a background task.
    Uses LocalSyncer instead of SharePoint/OneDrive APIs.

    For each source folder:
      1. scan_source()  — detect changed files via mtime + xxhash
      2. copy_file()    — chunked copy with .ghosttmp safety + verify
      3. record_file()  — write to manifest

    Progress is written to _active_run so /run/status streams live to the UI.
    """
    global _active_run

    if _active_run and _active_run.get("status") == "running":
        logger.warning("Backup already running — skipping duplicate trigger")
        return

    # SSD pre-flight check
    ssd_status = _syncer.check_ssd()
    if ssd_status["status"] != "ok":
        err = ssd_status.get("error", "SSD unavailable")
        logger.error(f"Backup aborted — {err}")
        await _reporter.alert_and_notify(
            level="error", title="Backup aborted — SSD unavailable",
            body=err, send_email=True,
        )
        return

    run_id = _manifest.create_run(full_backup=full)
    if _scheduler:
        _scheduler.set_current_run_id(run_id)

    _active_run = {
        "run_id":            run_id,
        "status":            "running",
        "started_at":        datetime.utcnow().isoformat(),
        "overall_pct":       0,
        "libraries":         {},    # key kept as 'libraries' for UI compat
        "files_transferred": 0,
        "files_skipped":     0,
        "files_failed":      0,
        "bytes_transferred": 0,
        "errors":            [],
        "feed":              [],    # last 50 file events for live UI
        "speed_bps":         0,     # bytes/s rolling estimate
    }

    try:
        target_sources = []
        for s in _config.get_enabled_sources():
            label = s.get("label") or s.get("name", "")
            if not sources or label in sources:
                target_sources.append(s)

        if not target_sources:
            raise RuntimeError("No enabled source folders configured")

        total_sources = len(target_sources)
        executor = ThreadPoolExecutor(max_workers=_config.concurrency)

        for idx, source in enumerate(target_sources):
            label = source.get("label") or source.get("name", "?")

            # Check source folder exists before scanning
            from pathlib import Path as _Path
            if not _Path(source["path"]).exists():
                _active_run["errors"].append({
                    "library": label,
                    "error":   f"Source folder not found: {source['path']}",
                })
                _active_run["libraries"][label] = {"status": "failed", "pct": 0,
                    "files_transferred": 0, "files_failed": 1, "bytes": 0}
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
                # Scan for changed files (runs in thread — blocks filesystem)
                changed_files, skipped = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    lambda s=source, f=full: _syncer.scan_source(s, force_full=f),
                )
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

                # Speed tracking
                _speed_window = {"bytes": 0, "ts": time.monotonic()}

                def _progress_cb(chunk_bytes: int) -> None:
                    _speed_window["bytes"] += chunk_bytes
                    elapsed = time.monotonic() - _speed_window["ts"]
                    if elapsed >= 1.0:
                        _active_run["speed_bps"] = int(
                            _speed_window["bytes"] / elapsed
                        )
                        _speed_window["bytes"] = 0
                        _speed_window["ts"]    = time.monotonic()

                for f_idx, file_meta in enumerate(changed_files):
                    # Bail out if run was cancelled via /run/stop
                    if _active_run.get("status") == "cancelled":
                        break

                    try:
                        backup_path = await asyncio.get_event_loop().run_in_executor(
                            executor,
                            lambda fm=file_meta: _syncer.copy_file(
                                fm, run_id, on_progress=_progress_cb
                            ),
                        )

                        _manifest.record_file(run_id, file_meta, backup_path)

                        lib_state["files_transferred"] += 1
                        lib_state["bytes"] += file_meta["size"]
                        _active_run["files_transferred"] += 1
                        _active_run["bytes_transferred"] += file_meta["size"]

                        feed_event = {
                            "time":    datetime.utcnow().strftime("%H:%M:%S"),
                            "file":    file_meta["name"],
                            "size_mb": round(file_meta["size"] / (1024 * 1024), 2),
                            "library": label,
                            "checksum_ok": True,
                        }
                        _active_run["feed"] = [feed_event] + _active_run["feed"][:49]

                    except Exception as file_err:
                        err_msg = str(file_err)
                        logger.error(f"[{label}] File failed: {file_meta['name']} — {err_msg}")
                        lib_state["files_failed"] += 1
                        _active_run["files_failed"] += 1
                        _active_run["errors"].append({
                            "file":    file_meta["name"],
                            "library": label,
                            "error":   err_msg,
                        })
                        _manifest.log(run_id, "ERROR",
                                      f"{file_meta['name']}: {err_msg}")

                        # Circuit breaker: >20% failure rate on this source
                        fail_rate = lib_state["files_failed"] / max(total_files, 1)
                        if fail_rate > _config.sources[0].circuit_breaker_threshold \
                                if _config.sources else fail_rate > 0.20:
                            pass  # use default 0.20
                        if fail_rate > 0.20 and lib_state["files_failed"] >= 5:
                            logger.error(
                                f"Circuit breaker tripped: {label} "
                                f"({fail_rate:.0%} failure)"
                            )
                            lib_state["status"] = "circuit_broken"
                            await _reporter.send_circuit_breaker_alert(
                                library=label,
                                fail_rate_pct=fail_rate * 100,
                                run_id=run_id,
                            )
                            break

                    lib_state["pct"] = round((f_idx + 1) / max(total_files, 1) * 100)
                    _active_run["overall_pct"] = round(
                        ((idx + lib_state["pct"] / 100) / total_sources) * 100
                    )

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

        executor.shutdown(wait=False)

        # Final status
        lib_statuses = [v["status"] for v in _active_run["libraries"].values()]
        if not lib_statuses or all(s == "success" for s in lib_statuses):
            final_status = "success"
        elif all(s in ("failed", "circuit_broken") for s in lib_statuses):
            final_status = "failed"
        else:
            final_status = "partial"

        _active_run["status"]       = final_status
        _active_run["overall_pct"]  = 100
        _active_run["finished_at"]  = datetime.utcnow().isoformat()

        _manifest.finalize_run(run_id, _active_run)

        # ── Fix 1: retry locked files ─────────────────────────────────────
        # Collect files that failed with a lock/permission error across all sources
        # and retry them once at the end of the run (user may have closed the file)
        locked_retries = [
            e for e in _active_run["errors"]
            if "locked" in e.get("error", "").lower()
            or "permission" in e.get("error", "").lower()
        ]
        if locked_retries:
            logger.info(f"Retrying {len(locked_retries)} locked file(s)…")
            for err_entry in locked_retries:
                src_path = err_entry.get("original_path") or err_entry.get("file", "")
                label    = err_entry.get("library", "")
                if not src_path:
                    continue
                from pathlib import Path as _P
                src = _P(src_path)
                if not src.exists():
                    continue
                try:
                    import os as _os
                    stat      = src.stat()
                    file_hash = _syncer._hash_file_direct(src)
                    file_meta = {
                        "source_label":  label,
                        "name":          src.name,
                        "original_path": str(src),
                        "rel_path":      str(src.relative_to(_P(
                            next((s["path"] for s in _config.get_enabled_sources()
                                  if s.get("label") == label), str(src.parent))
                        ))),
                        "size":  stat.st_size,
                        "mtime": stat.st_mtime,
                        "xxhash": file_hash,
                    }
                    backup_path = await asyncio.get_event_loop().run_in_executor(
                        None, lambda fm=file_meta: _syncer.copy_file(fm, run_id)
                    )
                    _manifest.record_file(run_id, file_meta, backup_path)
                    _active_run["files_transferred"] += 1
                    _active_run["files_failed"]      -= 1
                    _active_run["errors"] = [
                        e for e in _active_run["errors"]
                        if e.get("original_path") != src_path
                    ]
                    logger.info(f"Locked file retry succeeded: {src.name}")
                except Exception as retry_err:
                    logger.warning(f"Locked file retry failed: {src.name} — {retry_err}")

        # ── Fix 2: backup the manifest DB to SSD after every run ──────────
        # If the host machine dies, the restore map is still on the SSD
        if _config.ssd_path:
            try:
                from pathlib import Path as _P
                import shutil as _shutil
                db_src  = _manifest._path
                db_dest = _P(_config.ssd_path) / ".ghostbackup" / "ghostbackup.db"
                db_dest.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(db_src), str(db_dest))
                logger.info(f"Manifest DB backed up to SSD: {db_dest}")
            except Exception as db_err:
                logger.warning(f"Manifest DB backup to SSD failed: {db_err}")

        await _reporter.send_run_report(_active_run)
        logger.info(f"Run #{run_id} complete — {final_status}")

        # Reset missed-backup alert flag so it doesn't re-fire after a recovery
        if final_status == "success" and _scheduler:
            _scheduler._missed_alerted = False

    except Exception as fatal_err:
        logger.error(f"Fatal backup error: {fatal_err}", exc_info=True)
        _active_run["status"]      = "failed"
        _active_run["finished_at"] = datetime.utcnow().isoformat()
        _manifest.finalize_run(run_id, _active_run)
        await _reporter.alert_and_notify(
            level="critical", title="GhostBackup fatal error",
            body=str(fatal_err), run_id=run_id, send_email=True,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

# Health
@app.get("/health")
async def health():
    return {
        "status":            "ok",
        "version":           "2.0.0",
        "scheduler_running": _scheduler.is_running() if _scheduler else False,
        "next_run":          _scheduler.next_run_time() if _scheduler else None,
    }


# SSD status  (new — Phase 2)
@app.get("/ssd/status")
async def ssd_status():
    return get_ssd_status(_config.ssd_path)


# Dashboard
@app.get("/dashboard")
async def dashboard():
    runs = _manifest.get_runs(limit=30)
    last = runs[0] if runs else None
    ssd  = get_ssd_status(_config.ssd_path)
    return {
        "runs":        runs,
        "last_run":    last,
        "ssd_storage": ssd,        # renamed from 'storage' — UI updated to match
        "next_run":    _scheduler.next_run_time() if _scheduler else None,
        "active_run":  _active_run,
    }


# Run control
@app.post("/run/start")
async def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    if _active_run and _active_run.get("status") == "running":
        raise HTTPException(409, "A backup run is already in progress")
    background_tasks.add_task(run_backup_job, req.full, req.sources)
    return {"message": "Backup job started", "full": req.full}


@app.post("/run/stop")
async def stop_run():
    global _active_run
    if not _active_run or _active_run.get("status") != "running":
        raise HTTPException(400, "No active run to stop")
    _active_run["status"]      = "cancelled"
    _active_run["finished_at"] = datetime.utcnow().isoformat()
    return {"message": "Run cancellation requested"}


@app.get("/run/status")
async def run_status():
    if not _active_run:
        return {"status": "idle"}
    return _active_run


# Run history & logs
@app.get("/runs")
async def get_runs(limit: int = 30, offset: int = 0):
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


# Config
@app.get("/config")
async def get_config():
    return _config.to_dict_safe()


@app.patch("/config")
async def update_config(req: ConfigUpdateRequest):
    updates = req.model_dump(exclude_none=True)
    watcher_enabled = updates.pop("watcher_enabled", None)
    _config.update(updates)
    if "schedule_time" in updates or "timezone" in updates:
        _scheduler.reschedule(_config.schedule_time, _config.timezone)
    # Re-init syncer so new ssd_path / settings take effect immediately
    global _syncer
    _syncer = LocalSyncer(_config, _manifest)
    # Handle watcher toggle
    if watcher_enabled is True and _watcher and not _watcher._running:
        _watcher.reload_sources()
    elif watcher_enabled is False and _watcher and _watcher._running:
        _watcher.stop()
    return {"message": "Config updated", "config": _config.to_dict_safe()}


@app.post("/config/sites")
async def add_site(req: SiteRequest):
    _config.add_site(req.model_dump(exclude_none=True))
    if _watcher:
        _watcher.reload_sources()
    return {"message": "Source added"}


@app.delete("/config/sites/{site_name}")
async def remove_site(site_name: str):
    removed = _config.remove_site(site_name)
    if not removed:
        raise HTTPException(404, f"Source '{site_name}' not found")
    if _watcher:
        _watcher.reload_sources()
    return {"message": "Source removed"}


# Restore  (Phase 2: pure local filesystem)
@app.post("/restore")
async def restore(req: RestoreRequest, background_tasks: BackgroundTasks):
    run = _manifest.get_run(req.run_id)
    if not run:
        raise HTTPException(404, f"Run #{req.run_id} not found")
    if run["status"] == "failed":
        raise HTTPException(400, "Cannot restore from a failed run")

    files = _manifest.get_files(req.run_id, library=req.library,
                                subfolder=req.subfolder)
    if not files:
        raise HTTPException(404, "No files found matching the restore criteria")

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

    # Run synchronously so UI knows when restore is actually complete
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: _syncer.restore_files(files, req.destination)
        )
        restored = result.get("restored", 0)
        failed   = result.get("failed", 0)
        return {
            "dry_run":      False,
            "message":      f"Restore complete — {restored} files written to {req.destination}",
            "files_count":  restored,
            "files_failed": failed,
            "destination":  req.destination,
            "errors":       result.get("errors", []),
        }
    except Exception as e:
        raise HTTPException(500, f"Restore failed: {e}")


# Settings
@app.patch("/settings/smtp")
async def update_smtp(req: SmtpUpdateRequest):
    _config.update_smtp(req.model_dump(exclude_none=True))
    return {"message": "SMTP settings updated"}


@app.post("/settings/smtp/test")
async def test_smtp():
    try:
        await _reporter.send_test_email()
        return {"message": "Test email sent successfully"}
    except Exception as e:
        raise HTTPException(500, f"SMTP test failed: {e}")


@app.patch("/settings/retention")
async def update_retention(req: RetentionUpdateRequest):
    if req.guard_days < 7:
        raise HTTPException(400, "Safety guard window cannot be less than 7 days")
    _config.update_retention(req.model_dump())
    return {"message": "Retention policy updated"}


@app.post("/settings/prune")
async def run_prune(background_tasks: BackgroundTasks):
    if _active_run and _active_run.get("status") == "running":
        raise HTTPException(409, "Cannot prune while a backup is running")
    background_tasks.add_task(_do_prune)
    return {"message": "Prune job started"}


async def _do_prune():
    loop = asyncio.get_event_loop()
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


# ── Phase 3: Watcher endpoints ───────────────────────────────────────────────

@app.get("/watcher/status")
async def watcher_status():
    """Return current watcher state — polled by the Settings UI card."""
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
        raise HTTPException(400, "No enabled source folders — add at least one source first")
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


# ── Alerts ────────────────────────────────────────────────────────────────────
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


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        reload=False,
    )
