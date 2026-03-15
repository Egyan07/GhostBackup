# GhostBackup

Automated local SSD backup desktop app for Red Parrot Accounting.  
Built with Electron + React (frontend) and Python FastAPI (backend).  
**No cloud, no Azure, no Microsoft credentials required.**

---

## What it does

- Backs up configured local source folders to a dedicated SSD destination
- Detects changed files via mtime + xxhash (only copies what actually changed)
- Runs a scheduled backup daily at 08:00 NPT
- Watches source folders in real-time and triggers incremental backups on file change (15s debounce)
- Sends desktop toast notifications and email alerts on failure
- Provides a full run history, per-file transfer log, and restore capability

---

## Quick start

```powershell
cd backend
pip install -r requirements.txt
cd ..
npm install
npm run dev
```

See [SETUP.md](SETUP.md) for complete first-time setup instructions.

---

## Module summary

| File | Role |
|---|---|
| `api.py` | FastAPI server on port 8765 — all endpoints, job orchestration |
| `config.py` | Config loader — reads config.yaml, SMTP password from env var |
| `syncer.py` | Local filesystem engine — mtime+xxhash scan, chunked copy, verify, restore, prune |
| `watcher.py` | Real-time watcher — watchdog observer, debounce, cooldown, asyncio dispatch |
| `manifest.py` | SQLite — run history, file records, file hash cache, logs |
| `scheduler.py` | APScheduler — 08:00 daily cron, watchdog stall detection, retry logic |
| `reporter.py` | Alert manager (in-memory) + SMTP HTML email reports |

---

## Architecture

```
Electron (main.js)
  │  spawns
  ▼
Python FastAPI (port 8765)
  ├─ BackupScheduler  →  runs run_backup_job() at 08:00 NPT
  ├─ FileWatcher      →  runs run_backup_job(sources=[label]) on file change
  └─ run_backup_job()
       ├─ LocalSyncer.scan_source()   →  mtime check → xxhash → changed file list
       ├─ LocalSyncer.copy_file()     →  .ghosttmp write → rename → xxhash verify
       └─ ManifestDB.record_file()    →  SQLite run + file records

React UI (port 3000 in dev)
  └─ fetches http://127.0.0.1:8765/*
```

---

## Key design decisions

**No cloud dependency** — all backup data stays on the local SSD. No Microsoft account, no Graph API, no internet required.

**Two-tier change detection** — mtime + size checked first (nanosecond precision, zero disk read). xxhash computed only if mtime changed. Files are skipped without reading if content is unchanged despite mtime delta (e.g. metadata writes).

**Crash-safe writes** — every file is written to `<dest>.ghosttmp` then renamed atomically. A power cut during copy leaves a `.ghosttmp` orphan, never a corrupt backup file.

**Post-copy verify** — after rename, xxhash of the destination is compared to the source. Mismatched files are deleted and the error reported immediately.

**Circuit breaker** — if >20% of files in a source fail in a single run, that source is aborted and an alert fires. Prevents silent partial backups.

**7-day prune guard** — the retention pruner refuses to delete any backup newer than `guard_days` (default 7). Hard minimum, cannot be set lower.

**Real-time watcher** — watchdog observer per source folder. Changes are debounced (15s default) to avoid triggering on rapid saves (e.g. Excel autosave). After a watcher-triggered run, a 120s cooldown prevents thrash on bulk file operations.

**Secrets never in config** — `config.yaml` contains zero secrets and is safe to commit. The only secret is `GHOSTBACKUP_SMTP_PASSWORD`, read exclusively from the environment.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Backend liveness + scheduler status |
| GET | `/dashboard` | Runs, last run, SSD stats, active run |
| GET | `/ssd/status` | SSD mount status, used/free/total GB |
| POST | `/run/start` | Trigger manual backup |
| POST | `/run/stop` | Cancel active run |
| GET | `/run/status` | Live run progress + file feed |
| GET | `/runs` | Run history |
| GET | `/runs/{id}/logs` | Per-run log entries |
| GET | `/runs/{id}/files` | Per-run file transfer records |
| GET | `/config` | Current config (no secrets) |
| PATCH | `/config` | Update config settings |
| POST | `/config/sites` | Add source folder |
| DELETE | `/config/sites/{name}` | Remove source folder |
| POST | `/restore` | Restore files from a backup run |
| GET | `/watcher/status` | Watcher running state + per-source info |
| POST | `/watcher/start` | Enable real-time watching |
| POST | `/watcher/stop` | Disable real-time watching |
| GET | `/alerts` | In-memory alert list |
| POST | `/alerts/{id}/dismiss` | Dismiss one alert |
| POST | `/alerts/dismiss-all` | Dismiss all alerts |
| PATCH | `/settings/smtp` | Update SMTP config |
| POST | `/settings/smtp/test` | Send test email |
| PATCH | `/settings/retention` | Update retention policy |
| POST | `/settings/prune` | Run retention prune now |
