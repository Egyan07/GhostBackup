# 👻 GhostBackup

> ⚠️ **Windows Only** — macOS and Linux are not supported. The app may not install or run correctly on those platforms.

### Local. Encrypted. Audited. Yours.

![CI](https://img.shields.io/github/actions/workflow/status/Egyan07/GhostBackup/ci.yml?label=CI)
![Backend Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen)
![Tests](https://img.shields.io/badge/tests-675%2B%20passing-brightgreen)
![GitHub issues](https://img.shields.io/github/issues/Egyan07/GhostBackup)
![GitHub last commit](https://img.shields.io/github/last-commit/Egyan07/GhostBackup)
![License](https://img.shields.io/github/license/Egyan07/GhostBackup)

**Author: [Egyan07](https://github.com/Egyan07)**

> 💡 Most small businesses back up to Dropbox or OneDrive and call it a day. But when your files contain client financials, legal documents, or personal records — you don't want them on someone else's server. GhostBackup keeps your backups local, encrypted, and under your control. No monthly bill. No breach notification letters.

---

GhostBackup is a secure automated backup system built with **Electron, React, and Python FastAPI**. Originally built for and actively deployed at Red Parrot Accounting (UK) — open source and free for any small business with similar needs.

---

> **In 30 seconds:** GhostBackup runs on a dedicated Windows machine, backs up your source folders to one or two local SSDs on a daily schedule, encrypts every file with AES-256-GCM, verifies integrity with xxhash, and emails you if anything fails. No cloud. No subscriptions. No IT staff required.

---

## ⚔️ How GhostBackup Compares

| Feature | GhostBackup | Backblaze B2 | Veeam Free | IDrive |
|---------|:-----------:|:------------:|:----------:|:------:|
| AES-256-GCM encryption | ✅ | ✅ | ❌ | ✅ |
| No cloud / no vendor dependency | ✅ | ❌ | ✅ | ❌ |
| No subscription cost | ✅ | ❌ | ✅ | ❌ |
| GUI dashboard + live run view | ✅ | ❌ | ✅ | ✅ |
| Per-file integrity verification (xxhash) | ✅ | ❌ | ❌ | ❌ |
| Email alerts on failure | ✅ | ✅ | ✅ | ✅ |
| Dry-run restore preview | ✅ | ❌ | ❌ | ❌ |
| Audit log with run history | ✅ | ❌ | ✅ | ✅ |
| Key fingerprint rotation detection | ✅ | ❌ | ❌ | ❌ |
| Open source | ✅ | ❌ | ❌ | ❌ |
| Windows native | ✅ | ✅ | ✅ | ✅ |
| Rate-limited REST API | ✅ | N/A | ❌ | ❌ |

> GhostBackup is purpose-built for small businesses that need real encryption, real audit trails, and zero recurring cost — without the complexity of enterprise backup suites.

---

## 📑 Table of Contents

- [How GhostBackup Compares](#️-how-ghostbackup-compares)
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
- [Disaster Recovery](#-disaster-recovery)
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

## ✨ Core Features

### 🛡️ Security & Privacy
| Feature | Description |
|---------|-------------|
| 🔐 Encryption at Rest | AES-256-GCM streaming encryption via Python `cryptography` library. Constant memory usage regardless of file size. Per-file random nonce. Versioned encryption header for future key rotation. Per-installation HKDF salt for stronger key isolation. |
| 🔐 Key Protection | Encryption keys stored in Windows Credential Manager (keyring). Automatic migration from `.env.local`. |
| 🔒 API Security | Auto-generated session token per launch via `crypto.randomBytes(32)`. All endpoints authenticated via `X-API-Key` header with timing-safe comparison (`hmac.compare_digest`). Rate limiting on sensitive endpoints (slowapi). |
| 🛡️ Immutable Window | Write-once-read-many (WORM) logic for the recent backup window (7 days). |
| 💾 Dual-SSD Redundancy | Primary and secondary SSD support. Combined with the original source, this provides 3 copies across 2 drives. Manual offsite copy support via [OFFSITE.md](OFFSITE.md). |

### 📊 Monitoring & Auditability
| Feature | Description |
|---------|-------------|
| ✅ Integrity Verification | On-demand xxhash verification of all backups. Automatic spot-checks on startup. |
| 🚀 Startup Self-Check | On launch, 5 random backup files are verified against the manifest. Critical alert on corruption. |
| 🧪 Restore Drill Tracking | Every restore is logged as a drill. Escalating reminders if no drill in 30/37/44 days. Audit-ready history. |
| 📧 Email Alerts | SMTP-based failure alerts and run summaries. Supports Gmail App Passwords and standard SMTP providers. |
| 🔔 Desktop Notifications | Windows toast notification on backup completion for all outcomes — success, partial, and failed. |
| 📝 Audit Logs | Detailed run history and alert logs persisted in a local SQLite database. |

### ⚡ Performance & UX
| Feature | Description |
|---------|-------------|
| ⏰ Scheduled Backups | Daily automated backups via APScheduler with configurable timezone support. |
| 👁️ Real-Time Watching | Watchdog-based file system monitor for instant incremental sync. |
| 🧪 Dry-Run Restore | Preview exactly which files will be restored before writing to disk. |
| 🧹 Automated Pruning | Smart retention policy (daily/weekly/yearly) that automatically deletes old backups to free up SSD space while respecting the immutable window. |
| 🌗 Dark/Light Theme | Toggle between dark (default) and light themes. Choice persists via localStorage. |

### 🛠️ Developer & Admin Tools
| Feature | Description |
|---------|-------------|
| 📋 SQLite Backend | Full backup history and per-file status stored in a local SQLite database. |
| 📤 Audit Log Export | Export full run history as a downloadable CSV from the Logs page. |
| 🏥 Deep Health Check | `GET /health/deep` returns comprehensive system status for monitors. |
| 🔢 Structured Errors | API errors include codes (GB-Exxx) with actionable fix suggestions. |

---

## ⚠️ Limitations

Before adopting GhostBackup, understand what it **does not** do:

| Limitation | Detail |
|------------|--------|
| **Windows only** | Requires Windows 10/11. No Linux or macOS support. |
| **Local drives only** | Backs up to directly attached drives (internal/external SSDs). No cloud, NAS, or network share support. |
| **No offsite copy** | GhostBackup handles local redundancy only. Offsite backup is your responsibility — see [OFFSITE.md](OFFSITE.md) for simple options using your existing tools. |
| **No deduplication** | Changed files are copied in full on each backup run. No block-level or byte-level dedup. |
| **Single machine** | No multi-user or networked deployment. If the machine is offline, no backup runs. |
| **Files only** | Restores individual files/folders — not OS images. Pair with Macrium Reflect Free for full system recovery. |
| **Locked files** | Files held open by other processes (e.g. open Excel) are retried but may be skipped. Check logs after each run. |
| **Long paths** | Paths over 260 characters may fail unless Windows long path support is enabled (`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`). |
| **Scale** | Tested up to ~50GB source data. Performance on 500GB+ datasets is untested. |
| **No external security audit** | Encryption and authentication use industry-standard libraries but have not been reviewed by a third-party security firm. |
| **Encryption key storage** | Key is stored in Windows Credential Manager (keyring) by default. Falls back to `.env.local` for CI environments. If the key is lost from all locations, all encrypted backups are permanently unrecoverable. |
| **Not legal compliance** | GhostBackup provides tools that *support* compliance. It is not a compliance certification. |

---

## 🚀 Quick Start

### Option A — Download Installer (Recommended)

1. Download the latest `GhostBackup_Setup.exe` from the **[Releases](https://github.com/Egyan07/GhostBackup/releases)** page.
2. Run the installer and follow the on-screen prompts.
3. Launch GhostBackup from your desktop or start menu.

### Option B — Manual Setup (~5 minutes)

If you prefer to install manually or use your existing Python/Node environments:

### Prerequisites

- Windows 10 or 11
- [Python 3.10+](https://www.python.org/downloads/) — **must be added to PATH during installation**
- [Node.js 22+](https://nodejs.org/)
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
   - Generate an AES-256 encryption key and per-installation HKDF salt, stored in Windows Credential Manager (falls back to `.env.local` in CI environments)
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
npm test                    # all tests (frontend + electron)
npm run test:frontend       # 260+ vitest tests
npm run test:electron       # 77 behavioral tests
npm run test:coverage       # frontend with coverage
cd backend && python -m pytest tests/ -v --cov=.  # 407 backend tests
```

| Suite | Tests | Coverage | CI |
|-------|-------|----------|----|
| Backend (pytest) | 407 | 90% line | ✅ |
| Frontend (Vitest) | 260+ | 75%+ stmt | ✅ |
| Electron (Vitest) | 77 | — | ✅ |

Covers: backup engine, all API endpoints, all 6 pages, all 8 components, IPC/preload/CSP, input validation, and auth edge cases. Not covered: full E2E Electron-to-disk pipeline (manual only).

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

All endpoints require the **X-API-Key header** except `/health`. Full OpenAPI schema available at `/openapi.json` when the backend is running.

| Group | Method | Endpoint | Description |
|-------|--------|----------|-------------|
| Core | GET | /health | Health check (no auth) |
| Core | GET | /dashboard | Dashboard summary stats |
| Core | GET | /health/deep | Comprehensive health check |
| Runs | POST | /run/start | Start a backup run |
| Runs | POST | /run/stop | Cancel the active run |
| Runs | GET | /run/status | Active run state |
| Runs | GET | /runs | Backup run history |
| Runs | GET | /runs/:id/logs | Log entries for a run |
| Runs | POST | /verify | Re-hash all backups, return counts |
| Restore | POST | /restore | Restore files (path traversal validated) |
| Config | GET | /config | Current configuration |
| Config | PATCH | /config | Update configuration |
| Config | GET | /config/audit | Configuration change audit trail |
| Config | POST | /config/sites | Add a source folder |
| Settings | PATCH | /settings/smtp | Update SMTP settings |
| Settings | POST | /settings/smtp/test | Send a test email |
| Settings | PATCH | /settings/retention | Update retention policy |
| Settings | POST | /settings/prune | Trigger prune job |
| Monitor | GET | /ssd/status | Disk usage and health |
| Monitor | GET | /alerts | In-app alert list |
| Monitor | POST | /alerts/dismiss-all | Dismiss all alerts |
| Monitor | GET | /watcher/status | File watcher state |

---

## ⚙️ Configuration

Location: `backend/config/config.yaml`
Template: `backend/config/config.yaml.example`

See `backend/config/config.yaml.example` for all options including SSD paths, encryption, sources, retention, schedule, circuit breaker threshold, and watcher settings.

---

## 🔑 Environment Variables

The encryption key is stored in Windows Credential Manager by default. `.env.local` is used as a fallback for CI/headless environments and must never be committed (already in `.gitignore`).

| Variable | Required | Description |
|----------|----------|-------------|
| `GHOSTBACKUP_ENCRYPTION_KEY` | Yes (if encryption enabled) | AES-256 key stored in Windows Credential Manager. **If lost, all encrypted backups are unrecoverable.** |
| `GHOSTBACKUP_HKDF_SALT` | Recommended | Per-installation salt for key derivation isolation. |
| `GHOSTBACKUP_SMTP_PASSWORD` | Yes (if email enabled) | SMTP password. For Gmail, use an App Password. |
| `GHOSTBACKUP_API_PORT` | No (default: 8765) | FastAPI backend port. |
| `GHOSTBACKUP_API_TOKEN` | Auto | Generated by Electron per launch. Do not set manually. |

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
│   └── tests/               ← 407 pytest tests
│
├── electron/
│   ├── main.js              ← Electron main process (spawns backend, tray)
│   └── preload.js           ← contextBridge API surface
│
├── src/
│   ├── GhostBackup.tsx      ← app shell + sidebar navigation
│   ├── main.tsx             ← React entry point + backend health poller
│   ├── api-client.ts        ← authenticated fetch wrapper (typed)
│   ├── types.ts             ← shared TypeScript interfaces
│   ├── styles.css           ← application styles
│   ├── components/          ← reusable UI components (8 .tsx files)
│   ├── pages/               ← full-page views (6 .tsx files)
│   └── tests/               ← 260+ vitest tests
│
├── screenshots/             ← README screenshots
├── OFFSITE.md               ← offsite backup guide
├── SETUP.md                 ← full setup guide
├── RECOVERY.md              ← disaster recovery guide
└── CHANGELOG.md             ← full version history
```

---

## 🔐 Security

| Layer | Implementation |
|-------|----------------|
| Encryption | AES-256-GCM via Python `cryptography` library. Streaming with constant memory. Per-file random nonce (`os.urandom`). Versioned header (v1) for key rotation support. Per-installation HKDF salt generated at setup for stronger key derivation isolation. **Fail-hard mode:** if encryption is enabled but key is missing or broken, the app refuses to start — no silent fallback to unencrypted backups. |
| API Authentication | Session token via `crypto.randomBytes(32)` per launch. Validated with `hmac.compare_digest` (timing-safe). Rate limiting on sensitive endpoints (slowapi). |
| Path Safety | Restore endpoint validates all paths against traversal attacks before any file operation. |
| Electron Sandbox | Chromium sandbox enabled. Fine-grained CSP with 10 directives: `script-src 'self'`, `connect-src` pinned to API port, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`. |
| Credential Storage | Secrets in `.env.local` with input sanitization on writes. Excluded from version control. |
| Database Integrity | SQLite with `PRAGMA synchronous=FULL`. File records committed every 100 inserts during a run — crash data loss limited to at most 100 files. WAL checkpoint after every run prevents unbounded WAL growth. Schema versioned with incremental delta migrations. Manifest DB backed up to SSD with 3-copy rotation after every run. |
| Key Rotation Safety | Each backed-up file stores a SHA-256 fingerprint of the encryption key used. On restore, a fingerprint mismatch triggers a warning — detects silent restore failures after key rotation. |
| Process Safety | Before killing a conflicting process on ports 8765 (API) and 8766 (notifications), GhostBackup verifies it's a Python/GhostBackup process. Will not kill unrelated processes. |
| Data Integrity | xxhash checksum computed at source, verified after every copy to primary and secondary drives. |
| Failure Protection | Configurable failure threshold (default 5%, min 3 files). If exceeded per library, that library aborts. |

**What's NOT covered:**
- No external penetration testing or third-party security audit
- Encryption key stored in Windows Credential Manager by default;
  `.env.local` fallback used in CI — protect with OS-level permissions
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
| Integrity verification | `/verify` endpoint re-hashes all backup files and returns verified/corrupt/missing counts to the UI |

**Your Responsibilities**
- **GDPR:** If backing up personal data, conduct your own data protection impact assessment. Consider how right-to-erasure requests interact with long-term retention.
- **Key management:** Back up your encryption key securely. If lost, all encrypted backups are permanently unrecoverable.
- **Restore testing:** Periodically verify you can actually restore from backups. GhostBackup provides the tools — you must verify they work for your data.
- **Offsite copy:** GhostBackup handles local redundancy only. You are responsible for maintaining an offsite copy — see [OFFSITE.md](OFFSITE.md) for recommended approaches.

---

## 🛠 Troubleshooting

| Problem | Fix |
|---------|-----|
| "Port already in use" | Quit via tray icon → Quit GhostBackup (X button just hides to tray) |
| "Backup service stopped unexpectedly" | Run `pip install -r backend/requirements.txt` then relaunch |
| Email alerts not arriving | Gmail needs an App Password, not your regular password. Host: `smtp.gmail.com`, port: `587` |
| Backup not running on schedule | Check sidebar status dot is green. Verify `schedule.time` and `schedule.timezone` in `config.yaml` |
| "No runs yet" after backup | Don't delete `backend/ghostbackup.db` — it stores all run history |
| Can't find backed-up file on SSD | Encrypted files use `.ghostenc` extension. Restore via the app, don't open directly |
| Network share / NAS? | Not supported. Local drives only |
| Power loss during backup | Run is marked failed, DB won't corrupt. Re-run backup on next launch |
| How to update | `git pull && pip install -r backend/requirements.txt && npm install --legacy-peer-deps` |
| Log files | `backend/logs/ghostbackup.log` or Logs & History page in the app |

---

## 🆘 Disaster Recovery

When things go wrong, refer to **[RECOVERY.md](RECOVERY.md)** for step-by-step recovery procedures covering:

- Lost encryption key
- Corrupted manifest database
- Deleted or corrupted `.env.local`
- SSD failure mid-backup
- Application won't start
- Verification finds corrupted files
- Prevention checklist

Keep a printed copy alongside your offsite backup drive.

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
