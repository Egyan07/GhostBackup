<div align="center">

# 👻 GhostBackup

### *Coded by Egyan*

<br>

**Automated Local SSD Backup Solution for RedParrot Accounting**

Built with Electron + React (Frontend) | Python FastAPI (Backend)

*No Cloud. No Azure. No Microsoft Credentials. Just Reliable Backups.*

<br>

![Electron](https://img.shields.io/badge/Electron-191970?style=for-the-badge&logo=electron&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)

---

</div>

## 🔥 Why GhostBackup?

**RedParrot Accounting** handles critical financial data daily — client records, tax files, invoices, and audit trails. Losing even one file could mean hours of rework or compliance issues.

**GhostBackup** was purpose-built for RedParrot to solve one problem:

> *"Back up everything, automatically, locally, and never lose a single file."*

No subscriptions. No cloud vendor lock-in. No internet dependency. Just a dedicated SSD and a tool that works silently in the background — like a ghost.

---

## ✨ Features at a Glance

| Feature | Description |
|---|---|
| 🔄 **Smart Change Detection** | Two-tier mtime + xxhash scanning — only copies what actually changed |
| ⏰ **Scheduled Daily Backup** | Runs automatically every day at **08:00 NPT** before the workday begins |
| 👁️ **Real-Time File Watching** | Detects file changes instantly with 15s debounce to avoid noise |
| 🛡️ **Crash-Safe Writes** | Atomic `.ghosttmp` → rename pattern — power cuts never corrupt backups |
| ✅ **Post-Copy Verification** | Every copied file is xxhash-verified after write |
| 🚨 **Failure Alerts** | Desktop toast notifications + SMTP email alerts on any failure |
| 📊 **Full Run History** | Complete audit trail — every run, every file, every transfer logged |
| ♻️ **One-Click Restore** | Restore any file from any backup run through the UI |
| 🧹 **Smart Retention** | Auto-prune old backups with a hard 7-day safety guard |
| 🔌 **Circuit Breaker** | Aborts if >20% of files fail — prevents silent partial backups |
| 🔒 **Zero Secrets in Config** | SMTP password lives only in environment variables |

---

## 🚀 Quick Start

```powershell
# Clone the repository
git clone https://github.com/Egyan07/GhostBackup.git
cd GhostBackup

# Install backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Install frontend dependencies
npm install

# Launch in development mode
npm run dev
📖 See SETUP.md for complete first-time setup instructions including SSD configuration and SMTP setup.

🏗️ Architecture
text

┌─────────────────────────────────────────────────────┐
│                   ELECTRON SHELL                     │
│                    (main.js)                          │
│                       │                              │
│                       │ spawns                       │
│                       ▼                              │
│  ┌─────────────────────────────────────────────────┐ │
│  │           PYTHON FASTAPI (port 8765)            │ │
│  │                                                 │ │
│  │  ┌──────────────┐  ┌────────────────────────┐   │ │
│  │  │  Scheduler   │  │    File Watcher        │   │ │
│  │  │  08:00 NPT   │  │  Real-time monitoring  │   │ │
│  │  │  daily cron   │  │  15s debounce          │   │ │
│  │  └──────┬───────┘  └───────────┬────────────┘   │ │
│  │         │                      │                │ │
│  │         ▼                      ▼                │ │
│  │  ┌─────────────────────────────────────────┐    │ │
│  │  │          run_backup_job()                │    │ │
│  │  │                                         │    │ │
│  │  │  1. LocalSyncer.scan_source()           │    │ │
│  │  │     → mtime check → xxhash → diff list  │    │ │
│  │  │                                         │    │ │
│  │  │  2. LocalSyncer.copy_file()             │    │ │
│  │  │     → .ghosttmp write → rename → verify │    │ │
│  │  │                                         │    │ │
│  │  │  3. ManifestDB.record_file()            │    │ │
│  │  │     → SQLite run + file records          │    │ │
│  │  └─────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │          REACT UI (port 3000 in dev)            │ │
│  │                                                 │ │
│  │    Dashboard │ Run History │ Restore │ Config   │ │
│  │                                                 │ │
│  │         fetches http://127.0.0.1:8765/*         │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
📦 Module Summary
Module	Role
api.py	FastAPI server on port 8765 — all endpoints, job orchestration
config.py	Config loader — reads config.yaml, SMTP password from env var
syncer.py	Local filesystem engine — mtime+xxhash scan, chunked copy, verify, restore, prune
watcher.py	Real-time watcher — watchdog observer, debounce, cooldown, asyncio dispatch
manifest.py	SQLite manager — run history, file records, hash cache, structured logs
scheduler.py	APScheduler — 08:00 daily cron, watchdog stall detection, retry logic
reporter.py	Alert manager (in-memory) + SMTP HTML email reports
🎯 Key Design Decisions
🚫 No Cloud Dependency
All backup data stays on the local SSD. No Microsoft account, no Graph API, no internet required. RedParrot's financial data never leaves the office network.

🔍 Two-Tier Change Detection
Mtime + size checked first (nanosecond precision, zero disk read). xxhash computed only if mtime changed. Files are skipped without reading if content is unchanged despite mtime delta (e.g., metadata-only writes).

💥 Crash-Safe Writes
Every file is written to <dest>.ghosttmp then renamed atomically. A power cut during copy leaves a .ghosttmp orphan — never a corrupt backup file.

✅ Post-Copy Verification
After rename, xxhash of the destination is compared to the source. Mismatched files are deleted immediately and the error reported.

🔌 Circuit Breaker
If >20% of files in a source fail in a single run, that source is aborted and an alert fires. This prevents silent partial backups that look successful but aren't.

🛡️ 7-Day Prune Guard
The retention pruner refuses to delete any backup newer than guard_days (default 7). Hard minimum — cannot be set lower, even by accident.

👁️ Real-Time Watcher
Watchdog observer per source folder. Changes are debounced (15s default) to avoid triggering on rapid saves (e.g., Excel autosave). After a watcher-triggered run, a 120s cooldown prevents thrash on bulk file operations.

🔒 Secrets Never in Config
config.yaml contains zero secrets and is safe to commit. The only secret is GHOSTBACKUP_SMTP_PASSWORD, read exclusively from the environment.

🌐 API Reference
System
Method	Path	Description
GET	/health	Backend liveness + scheduler status
GET	/dashboard	Runs, last run, SSD stats, active run
GET	/ssd/status	SSD mount status, used/free/total GB
Backup Operations
Method	Path	Description
POST	/run/start	Trigger manual backup
POST	/run/stop	Cancel active run
GET	/run/status	Live run progress + file feed
POST	/restore	Restore files from a backup run
Run History
Method	Path	Description
GET	/runs	Full run history
GET	/runs/{id}/logs	Per-run log entries
GET	/runs/{id}/files	Per-run file transfer records
Configuration
Method	Path	Description
GET	/config	Current config (no secrets)
PATCH	/config	Update config settings
POST	/config/sites	Add source folder
DELETE	/config/sites/{name}	Remove source folder
File Watcher
Method	Path	Description
GET	/watcher/status	Watcher running state + per-source info
POST	/watcher/start	Enable real-time watching
POST	/watcher/stop	Disable real-time watching
Alerts
Method	Path	Description
GET	/alerts	In-memory alert list
POST	/alerts/{id}/dismiss	Dismiss one alert
POST	/alerts/dismiss-all	Dismiss all alerts
Settings
Method	Path	Description
PATCH	/settings/smtp	Update SMTP config
POST	/settings/smtp/test	Send test email
PATCH	/settings/retention	Update retention policy
POST	/settings/prune	Run retention prune now
🖥️ Tech Stack
Layer	Technology
Desktop Shell	Electron
Frontend	React + Vite
Backend	Python FastAPI
Database	SQLite (via ManifestDB)
File Hashing	xxhash (fast, non-cryptographic)
Scheduling	APScheduler
File Watching	Python Watchdog
Notifications	Desktop Toasts + SMTP Email
📁 Project Structure
text

GhostBackup/
├── assets/              # App icons and static assets
├── backend/             # Python FastAPI backend
│   ├── api.py           # Main API server
│   ├── config.py        # Configuration loader
│   ├── syncer.py        # File sync engine
│   ├── watcher.py       # Real-time file watcher
│   ├── manifest.py      # SQLite database manager
│   ├── scheduler.py     # Backup scheduler
│   ├── reporter.py      # Alert & email manager
│   └── requirements.txt # Python dependencies
├── config/              # Configuration files
├── electron/            # Electron main process
├── src/                 # React frontend source
├── package.json         # Node.js dependencies
├── vite.config.js       # Vite build config
├── SETUP.md             # Setup instructions
└── README.md            # This file
⚙️ Configuration
GhostBackup uses a config.yaml file for all settings:

YAML

# Backup sources
sources:
  - label: "Client Records"
    path: "D:\\RedParrot\\Clients"
  - label: "Tax Files"
    path: "D:\\RedParrot\\TaxDocs"

# Backup destination (SSD)
destination: "E:\\GhostBackups"

# Schedule
schedule_time: "08:00"
timezone: "Asia/Kathmandu"

# Retention
retention_days: 30
guard_days: 7

# Watcher
debounce_seconds: 15
cooldown_seconds: 120
🔐 SMTP Password: Set via environment variable GHOSTBACKUP_SMTP_PASSWORD — never stored in config files.

🤝 Built For
<div align="center">
🦜 RedParrot Accounting
Protecting your financial data, one backup at a time.

GhostBackup ensures that RedParrot Accounting's critical business data — client records, tax filings, invoices, and audit documentation — is automatically backed up, verified, and always recoverable.

</div>
<div align="center">
👻 GhostBackup — Silent. Reliable. Always watching.

Coded by Egyan

© 2025 RedParrot Accounting. All rights reserved.

</div> ```
