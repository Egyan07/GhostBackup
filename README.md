# 👻 GhostBackup

> ⚠️ **Windows Only** — macOS and Linux are not supported. The app may not install or run correctly on those platforms.

### Automated Backup with Encryption & Audit Logging

![CI](https://img.shields.io/github/actions/workflow/status/Egyan07/GhostBackup/ci.yml?label=CI)
![Backend Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)
![Tests](https://img.shields.io/badge/tests-379%20passing-brightgreen)
![GitHub issues](https://img.shields.io/github/issues/Egyan07/GhostBackup)
![GitHub last commit](https://img.shields.io/github/last-commit/Egyan07/GhostBackup)
![License](https://img.shields.io/github/license/Egyan07/GhostBackup)

**Author: [Egyan07](https://github.com/Egyan07)**

GhostBackup is a secure automated backup system built with **Electron, React, and Python FastAPI**. Originally built for and actively deployed at Red Parrot Accounting (UK) — open source and free for any small business with similar needs.

---

> **In 30 seconds:** GhostBackup runs on a dedicated Windows machine, backs up your source folders to one or two local SSDs on a daily schedule, encrypts every file with AES-256-GCM, verifies integrity with xxhash, and emails you if anything fails. No cloud. No subscriptions. No IT staff required.

---

## 📑 Table of Contents

- [Screenshots](#-screenshots)
- [Tech Stack](#-tech-stack)
- [Features](#-features)
- [Limitations](#-limitations)
- [Quick Start](#-quick-start)
- [Testing](#-testing)
- [Architecture](#-architecture)
- [API Endpoints](#-api-endpoints)
- [Configuration](#-configuration)
- [Environment Variables](#-environment-variables)
- [Project Structure](#-project-structure)
- [Security](#-security)
- [Retention & Auditability](#-retention--auditability)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [Use Cases](#-use-cases)
- [License](#-license)
- [Changelog](#-changelog)

---

## 📸 Screenshots

| Dashboard | Live Run | Restore |
|-----------|----------|---------|
| ![Dashboard](screenshots/Dashboard.png) | ![Live Run](screenshots/Live%20Run.png) | ![Restore](screenshots/Restore.png) |
| *Last run summary, SSD usage, and next scheduled backup* | *Live progress, per-library status, and file feed during an active run* | *Date and library selection with dry-run preview mode* |

| Email Alert |
|-------------|
| ![Email Alert](screenshots/Email%20Alerts.png) |
| *SMTP verification email confirming alerts are configured correctly* |

---

## 🧰 Tech Stack

![Electron](https://img.shields.io/badge/Electron-191970?style=for-the-badge&logo=electron&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔐 Encryption at Rest | AES-256-GCM streaming encryption via Python `cryptography` library. Constant memory usage regardless of file size. Per-file random nonce. Versioned encryption header for future key rotation. |
| 🔒 API Security | Auto-generated session token per launch via `crypto.randomBytes(32)`. All endpoints authenticated via `X-API-Key` header with timing-safe comparison (`hmac.compare_digest`). |
| 💾 Dual-SSD Redundancy | Primary and secondary SSD support. Combined with the original source, this gives you 3 copies across 2 drives. Offsite copy is your responsibility — GhostBackup handles the local copies. |
| ⏰ Scheduled Backups | Daily automated backups via APScheduler with configurable time and timezone. |
| 👁️ Real-Time File Watching | Watchdog-based file system monitor. Detects changes and triggers incremental backup (15s debounce, 120s cooldown between triggers). |
| 🛑 Failure Threshold Abort | If more than 5% of files fail during a library run (minimum 3 failures), that library is aborted. Other libraries continue. Threshold is configurable. |
| ✅ Integrity Verification | `/verify` endpoint re-hashes every backed-up file using xxhash and compares against stored checksums. |
| 📚 Audit Trail | Every configuration change is logged with UTC timestamp and hostname. Full backup history with per-file status stored in SQLite. |
| 📧 Email Alerts | SMTP-based failure alerts and run summaries. Supports Gmail App Passwords and standard SMTP providers. |

---

## ⚠️ Limitations

Before adopting GhostBackup, understand what it **does not** do:

| Limitation | Detail |
|------------|--------|
| **Windows only** | Requires Windows 10/11. No Linux or macOS support. |
| **Local drives only** | Backs up to directly attached drives (internal/external SSDs). No cloud, NAS, or network share support. |
| **No offsite copy** | GhostBackup handles local redundancy only. Offsite backup is your responsibility. |
| **No deduplication** | Changed files are copied in full on each backup run. No block-level or byte-level dedup. |
| **Single machine** | No multi-user or networked deployment. If the machine is offline, no backup runs. |
| **Files only** | Restores individual files/folders — not OS images. Pair with Macrium Reflect Free for full system recovery. |
| **Locked files** | Files held open by other processes (e.g. open Excel) are retried but may be skipped. Check logs after each run. |
| **Long paths** | Paths over 260 characters may fail unless Windows long path support is enabled (`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`). |
| **Scale** | Tested up to ~50GB source data. Performance on 500GB+ datasets is untested. |
| **No external security audit** | Encryption and authentication use industry-standard libraries but have not been reviewed by a third-party security firm. |
| **Encryption key in plaintext** | The key is stored in `.env.local` on disk. If you lose it, **all encrypted backups are permanently unrecoverable.** |
| **Not legal compliance** | GhostBackup provides tools that *support* compliance. It is not a compliance certification. |

---

## 🚀 Quick Start

**Windows guided setup (~5 minutes):**

### Prerequisites

- Windows 10 or 11
- [Python 3.10+](https://www.python.org/downloads/) — **must be added to PATH during installation**
- [Node.js 18+](https://nodejs.org/)
- At least one dedicated backup drive (SSD recommended)
- ~200MB free disk space for dependencies
- Internet connection required during install (for `pip install` and `npm install`)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Egyan07/GhostBackup.git
   cd GhostBackup
   ```

2. Run the guided installer:
   ```
   install.bat
   ```
   This will:
   - Install Python and Node.js dependencies
   - Prompt you to select backup source folders
   - Prompt you to select primary (and optionally secondary) SSD drive
   - Generate an AES-256 encryption key and store it in `.env.local`
   - Create `backend/config/config.yaml` from the template

3. Launch GhostBackup:
   ```
   start.bat
   ```

> **Note:** Admin privileges are not required. Expected install time: 2–5 minutes.

> Full step-by-step guide: **[SETUP.md](SETUP.md)**

### If something goes wrong during install

- **Python not found:** Reinstall Python and check "Add to PATH" during setup
- **Permission errors:** Run `install.bat` as Administrator
- **Port 8765 in use:** Another instance may be running in the tray. Right-click tray icon → Quit GhostBackup, then retry

---

## 🧪 Testing

```bash
# Backend — 319 tests, 88% line coverage
cd backend
python -m pytest tests/ -v --cov=. --cov-report=term-missing

# Frontend — 60 tests
npm test
```

| Suite | Tests | Coverage | Type | CI |
|-------|-------|----------|------|----|
| Backend | 319 | 88% line | Unit + integration | ✅ GitHub Actions |
| Frontend | 60 | — | Unit (Vitest) | ✅ GitHub Actions |

**What's tested:**
- Backup engine (scan, encrypt, copy, verify, prune)
- API endpoints (auth, config, runs, restore, alerts)
- Configuration management and audit logging
- Scheduler and file watcher lifecycle
- Email alert formatting and delivery
- Failure threshold behavior

**What's not tested:**
- End-to-end Electron → backend → disk pipeline (manual testing only)
- Performance at scale beyond ~50GB
- Multi-drive failure scenarios

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ ELECTRON (main.js)                                          │
│ • Generates API token (crypto.randomBytes)                  │
│ • Spawns Python backend as child process                    │
│ • System tray integration                                   │
│ • If Electron exits, Python process is terminated           │
└──────────────────────────┬──────────────────────────────────┘
                           │ token via environment
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ FASTAPI BACKEND (port 8765)                                 │
│                                                             │
│ 🔒 Auth Middleware (X-API-Key on all routes except /health) │
│                                                             │
│ ⏰ APScheduler          👁️ Watchdog File Watcher             │
│ (daily cron job)        (15s debounce, 120s cooldown)       │
│                                                             │
│ Backup Engine (syncer.py)                                   │
│  ├─ Scan source folders for new/changed files               │
│  ├─ Encrypt each file (AES-256-GCM, per-file nonce, 4MB chunks) │
│  ├─ Copy to primary SSD (and secondary if configured)       │
│  ├─ Verify copy integrity (xxhash comparison)               │
│  ├─ Abort library if failure rate exceeds threshold (5%)    │
│  └─ Log every file result to SQLite                         │
│                                                             │
│ SQLite Database                                             │
│  ├─ Backup runs with timestamps and status                  │
│  ├─ Per-file records (hash, size, status, error)            │
│  └─ Configuration audit trail                               │
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │ HTTP (localhost only, polling)
┌──────────────────────────┴──────────────────────────────────┐
│ REACT FRONTEND (Chromium sandbox enabled, CSP active)       │
│ • Dashboard  • Live Run  • Logs                             │
│ • Restore    • Settings  • Alert Bell                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔌 API Endpoints

All endpoints require the **X-API-Key header** except `/health`.

**Core**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check (no auth required) |
| GET | /dashboard | Dashboard summary stats |

**Backup Runs**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /run/start | Start a backup run |
| POST | /run/stop | Cancel the active run |
| GET | /run/status | Active run state |
| POST | /verify | Re-hash all backed-up files and report mismatches |
| GET | /runs | Backup run history |
| GET | /runs/:id | Single run detail |
| GET | /runs/:id/logs | Per-file log entries for a run |

**Restore**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /restore | Restore files (path traversal validated) |

**Configuration**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /config | Current configuration |
| PATCH | /config | Update configuration |
| GET | /config/audit | Configuration change audit trail |
| POST | /config/sites | Add a backup source folder |
| PATCH | /config/sites/:name | Update a source folder |
| DELETE | /config/sites/:name | Remove a source folder |

**Settings**

| Method | Endpoint | Description |
|--------|----------|-------------|
| PATCH | /settings/smtp | Update SMTP email settings |
| POST | /settings/smtp/test | Send a test email |
| PATCH | /settings/retention | Update retention policy |
| POST | /settings/prune | Manually trigger prune job |
| POST | /settings/encryption/generate-key | Generate a new encryption key |

**Monitoring**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /ssd/status | Disk usage and health for configured drives |
| GET | /alerts | In-app alert list |
| POST | /alerts/:id/dismiss | Dismiss a single alert |
| POST | /alerts/dismiss-all | Dismiss all alerts |
| GET | /watcher/status | File watcher running state |
| POST | /watcher/start | Start file watcher |
| POST | /watcher/stop | Stop file watcher |

---

## ⚙️ Configuration

Location: `backend/config/config.yaml`
Template: `backend/config/config.yaml.example`

```yaml
ssd_path: "D:\\GhostBackup"
secondary_ssd_path: "E:\\GhostBackup2"   # optional — leave blank to disable

encryption:
  enabled: true   # requires GHOSTBACKUP_ENCRYPTION_KEY in .env.local

sources:
  - label: "Client Records"
    path: "C:\\Users\\admin\\SharePoint\\Red Parrot\\Clients"
    enabled: true

retention:
  daily_days: 365         # keep daily backups for 1 year
  weekly_days: 2555       # keep weekly backups for 7 years
  compliance_years: 7     # minimum retention floor
  guard_days: 7           # prevent accidental deletion of recent backups

schedule:
  time: "08:00"
  timezone: "Europe/London"

circuit_breaker_threshold: 0.05   # abort library if >5% of files fail

watcher:
  debounce_seconds: 15    # wait this long after the last change before triggering a backup
  cooldown_seconds: 120   # minimum gap between two watcher-triggered backup runs
```

---

## 🔑 Environment Variables

Store secrets in `.env.local` in the project root. This file must never be committed (already in `.gitignore`).

```bash
GHOSTBACKUP_ENCRYPTION_KEY=your-base64-key-here
GHOSTBACKUP_SMTP_PASSWORD=your-smtp-password
# GHOSTBACKUP_API_PORT=8765
```

| Variable | Required | Description |
|----------|----------|-------------|
| `GHOSTBACKUP_ENCRYPTION_KEY` | Yes (if encryption enabled) | Base64-encoded Fernet key — HKDF-derived to 256-bit AES. Generated by `install.bat`. **If lost, all encrypted backups are unrecoverable.** |
| `GHOSTBACKUP_SMTP_PASSWORD` | Yes (if email alerts enabled) | SMTP password. For Gmail, use an App Password. |
| `GHOSTBACKUP_API_PORT` | No (default: 8765) | Port for the FastAPI backend. |
| `GHOSTBACKUP_API_TOKEN` | Auto | Generated by Electron on each launch. Do not set manually. |
| `GHOSTBACKUP_DB_PATH` | No (default: `backend/ghostbackup.db`) | Override the SQLite database path. Useful when running the backend standalone outside the project directory. |

---

## 📂 Project Structure

```
GhostBackup/
│
├── install.bat              ← guided first-time setup
│
├── backend/
│   ├── config/
│   │   ├── config.yaml.example
│   │   └── config.yaml      ← your configuration (generated by install.bat)
│   ├── api.py               ← FastAPI server
│   ├── config.py            ← ConfigManager (load, validate, audit)
│   ├── manifest.py          ← SQLite database (runs, files, audit trail)
│   ├── reporter.py          ← AlertManager + SMTP email delivery
│   ├── scheduler.py         ← APScheduler daily job
│   ├── setup_helper.py      ← called by install.bat for guided setup
│   ├── syncer.py            ← backup engine (scan, encrypt, copy, verify, prune)
│   ├── utils.py             ← shared helpers (fmt_bytes, fmt_duration)
│   ├── watcher.py           ← watchdog real-time file watcher
│   └── tests/               ← 278 pytest tests
│
├── electron/
│   ├── main.js              ← Electron main process (spawns backend, tray)
│   └── preload.js           ← contextBridge API surface
│
├── src/
│   ├── GhostBackup.jsx      ← app shell + sidebar navigation
│   ├── main.jsx             ← React entry point + backend health poller
│   ├── api-client.js        ← authenticated fetch wrapper
│   ├── styles.css           ← application styles
│   ├── splash.css           ← splash/loading screen styles
│   ├── components/          ← reusable UI components
│   ├── pages/               ← full-page views (Dashboard, Restore, Settings, etc.)
│   └── tests/               ← 60 vitest tests
│
├── screenshots/             ← README screenshots
├── SETUP.md                 ← full setup guide
└── CHANGELOG.md             ← full version history
```

---

## 🔐 Security

| Layer | Implementation |
|-------|----------------|
| Encryption | AES-256-GCM via Python `cryptography` library. Streaming with constant memory. Per-file random nonce (`os.urandom`). Versioned header (v1) for key rotation support. |
| API Authentication | Session token via `crypto.randomBytes(32)` per launch. Validated with `hmac.compare_digest` (timing-safe). |
| Path Safety | Restore endpoint validates all paths against traversal attacks before any file operation. |
| Electron Sandbox | Chromium sandbox enabled. CSP enforced in both dev and production builds. |
| Credential Storage | Secrets in `.env.local` with input sanitization on writes. Excluded from version control. |
| Database Integrity | SQLite with `PRAGMA synchronous=FULL` and batched commits to prevent corruption on unexpected shutdown. |
| Process Safety | Before killing a conflicting process on port 8765, GhostBackup verifies it's a Python/GhostBackup process. Will not kill unrelated processes. |
| Data Integrity | xxhash checksum computed at source, verified after every copy to primary and secondary drives. |
| Failure Protection | Configurable failure threshold (default 5%, min 3 files). If exceeded per library, that library aborts. |

**What's NOT covered:**
- No external penetration testing or third-party security audit
- Encryption key stored in plaintext in `.env.local` — protect with OS-level permissions
- API is localhost-only with no TLS (acceptable for local Electron ↔ backend communication)

**Vulnerability Reporting:**
Open a GitHub issue or contact the author directly. Do not include exploit details in public issues.

---

## 📜 Retention & Auditability

> **Disclaimer:** GhostBackup provides tools that *support* regulatory compliance — retention policies, audit trails, encryption at rest, and integrity verification. It is not a compliance certification. Consult a qualified legal or compliance professional for your jurisdiction (e.g. UK Companies Act 2006, GDPR, HMRC record-keeping).

**Retention Settings**

| Policy | Default | Purpose |
|--------|---------|---------|
| Daily retention | 365 days | Keep daily snapshots for 1 year |
| Weekly retention | 2,555 days | Keep weekly snapshots for 7 years |
| Compliance floor | 7 years | Minimum retention — cannot be reduced below this |
| Guard days | 7 days | Prevents accidental pruning of the most recent backups |

**Audit Capabilities**

| Capability | Detail |
|------------|--------|
| Configuration audit trail | Every config change logged with timestamp, hostname, and previous value |
| Backup run history | Every run recorded with start/end time, file count, success/failure counts |
| Per-file records | Each file's hash, size, status, and any error message stored in SQLite |
| Integrity verification | `/verify` endpoint re-hashes all backup files and reports any mismatches |

**Your Responsibilities**
- **GDPR:** If backing up personal data, conduct your own data protection impact assessment. Consider how right-to-erasure requests interact with long-term retention.
- **Key management:** Back up your encryption key securely. If lost, all encrypted backups are permanently unrecoverable.
- **Restore testing:** Periodically verify you can actually restore from backups. GhostBackup provides the tools — you must verify they work for your data.
- **Offsite copy:** GhostBackup handles local redundancy only. You are responsible for maintaining an offsite copy.

---

## 🛠 Troubleshooting

**Q: I get "port already in use" every time I open the app.**

**A:** Closing with the X button hides the app to tray — it was still running. Always quit via File → Exit or right-click tray icon → Quit GhostBackup. This fully exits and releases port 8765.

---

**Q: The splash screen shows "backup service stopped unexpectedly (exit code 1)".**

**A:** Your Python dependencies are out of sync. Run:
```
pip install -r backend/requirements.txt
```
Then relaunch via `start.bat`.

---

**Q: Email alerts aren't arriving.**

**A:** If using Gmail, you need an App Password — not your regular password. Generate one at `https://myaccount.google.com/apppasswords`. In Settings configure: SMTP host `smtp.gmail.com`, port `587`, your Gmail in both From and Recipients. Save, then click Send Test Email.

---

**Q: The backup isn't running at the scheduled time.**

**A:** Check the sidebar status dot — green means running, grey/red means stopped (restart the app). Also verify `schedule.time` and `schedule.timezone` in `config.yaml` match your intended schedule.

---

**Q: The dashboard shows "No runs yet" even after a backup completed.**

**A:** The dashboard reads from `backend/ghostbackup.db`. If you moved or deleted this file, history is lost. Do not delete it — it contains your entire backup run history and audit trail.

---

**Q: A file was backed up but I can't find it on the SSD.**

**A:** Encrypted backups are stored with a `.ghostenc` extension and are not human-readable. Restore them through GhostBackup's Restore page — do not try to open them directly.

---

**Q: Can I back up to a network share or NAS?**

**A:** No. GhostBackup currently supports only directly attached drives. Network and cloud backup are not supported.

---

**Q: What happens if power is lost during a backup?**

**A:** The current run is marked as failed. SQLite uses `PRAGMA synchronous=FULL` so the database will not corrupt. On next launch, run a new backup normally — partially written files will be re-copied.

---

**Q: How do I update GhostBackup?**

**A:** Pull the latest changes and reinstall dependencies:
```bash
git pull
pip install -r backend/requirements.txt
npm install
```
Your `config.yaml` and `.env.local` will not be overwritten.

---

**Q: Where are the log files for undiagnosed issues?**

**A:** Logs are written to `backend/logs/` and also visible in the app under Logs & History. For backend errors not shown in the UI, check `backend/logs/ghostbackup.log`. You can filter by INFO, WARN, and ERROR levels in the Logs page.

---

## 🤝 Contributing

Originally built for Red Parrot Accounting, now open-sourced under MIT. Contributions are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b fix/your-fix`)
3. Run tests before submitting:
   ```bash
   cd backend && python -m pytest tests/ -v
   npm test
   ```
4. Open a pull request with a clear description of what changed and why

**Code style:** Follow existing patterns in the codebase. Run `eslint src` for frontend and `flake8 backend/` for backend before submitting. No new dependencies without discussion.

**Areas where contributions are especially welcome:**
- Linux/macOS support
- Network drive / NAS support
- Additional test coverage (especially E2E and restore scenarios)
- Documentation improvements

---

## 💼 Use Cases

- **Accounting firms** — long-term retention supporting UK Companies Act 2006 and HMRC requirements
- **Legal offices** — encrypted client file backups with full audit trail
- **Financial services** — scheduled, verifiable backups with failure alerting
- **Medical practices** — encrypted patient record backups (verify GDPR/NHS DSPT requirements separately)
- **Any small business** — that needs encrypted, automated, auditable local backups without cloud dependency

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for full text.

---

## 📋 Changelog

Full version history available in **[CHANGELOG.md](CHANGELOG.md)**.

---

*👻 GhostBackup — Silent. Secure. Auditable.*
