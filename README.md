# 👻 GhostBackup

### Automated Backup with Encryption & Compliance

![GitHub stars](https://img.shields.io/github/stars/Egyan07/GhostBackup?style=social)
![GitHub forks](https://img.shields.io/github/forks/Egyan07/GhostBackup?style=social)
![GitHub issues](https://img.shields.io/github/issues/Egyan07/GhostBackup)
![GitHub last commit](https://img.shields.io/github/last-commit/Egyan07/GhostBackup)
![License](https://img.shields.io/github/license/Egyan07/GhostBackup)

**Coded by Egyan**

GhostBackup is a secure automated backup system built with **Electron, React, and Python FastAPI**.
It is designed for environments requiring **encrypted backups, long-term retention, auditability, and automated monitoring**, such as accounting firms and regulated businesses.

The system performs encrypted backups, supports multi-disk redundancy, verifies file integrity, and enforces compliance-level retention policies.

---

# 🧰 Tech Stack

Electron + React Frontend
Python FastAPI Backend
SQLite Database

![Electron](https://img.shields.io/badge/Electron-191970?style=for-the-badge\&logo=electron\&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge\&logo=react\&logoColor=61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge\&logo=fastapi\&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge\&logo=python\&logoColor=white)

---

# ✨ Features

| Feature                     | Description                                           |
| --------------------------- | ----------------------------------------------------- |
| 🔐 Encryption at Rest       | AES-256-GCM streaming encryption (constant memory)    |
| 🔒 API Security             | Auto-generated session API tokens                     |
| 📜 Compliance Retention     | Built-in retention policy enforcement                 |
| 💾 3-2-1 Backup Strategy    | Primary and secondary storage support                 |
| ⏰ Scheduled Backups         | Daily automated backups using configured time + timezone |
| 👁️ Real-Time File Watching | File system monitoring with debounce                  |
| 🔌 Circuit Breaker          | Stops backup if more than 5% of files fail            |
| ✅ Integrity Verification    | `/verify` endpoint re-hashes backups                  |
| 📚 Audit Trail              | All configuration changes logged                      |

---

# 🚀 Quick Start

**Windows — one command setup:**

1. Install [Python 3.10+](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/) if not already installed
2. Clone the repository and double-click **`install.bat`**
3. Follow the prompts — paths, SSD drive, and encryption key are all configured automatically
4. Double-click **`start.bat`** to launch

Full step-by-step instructions are available in **SETUP.md**.

---

# 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ ELECTRON                                                    │
│ • Generates API token (crypto.randomBytes)                  │
│ • Spawns Python backend process                             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ FASTAPI BACKEND (default port 8765; configurable via        │
│ GHOSTBACKUP_API_PORT and used end-to-end by Electron + UI)  │
│                                                             │
│ 🔒 Authentication Middleware                                │
│ Requires X-API-Key header for all endpoints except /health  │
│                                                             │
│ ⏰ Scheduler                                                │
│ 👁️ File Watcher                                             │
│                                                             │
│ Backup Engine                                               │
│  ├─ 🔐 Encrypt files (AES-256-GCM streaming)                 │
│  ├─ 💾 Copy to primary and secondary drives                 │
│  ├─ ✅ Verify integrity using xxhash                        │
│  └─ 📚 Log results to SQLite                                │
└─────────────────────────────────────────────────────────────┘
                           ▲
┌──────────────────────────┴──────────────────────────────────┐
│ REACT FRONTEND                                              │
│ • Dashboard                                                 │
│ • Backup history                                            │
│ • Restore interface                                         │
│ • Compliance monitoring                                     │
│ • Exponential backoff polling                               │
└─────────────────────────────────────────────────────────────┘
```

---

# 🔌 API Endpoints

All endpoints require the **X-API-Key header** except `/health`.

| Method | Endpoint                                  | Description                        |
| ------ | ----------------------------------------- | ---------------------------------- |
| GET    | /health                                   | Health check (no auth required)    |
| GET    | /dashboard                                | Dashboard summary stats            |
| GET    | /run/status                               | Active run state                   |
| POST   | /run/start                                | Start backup                       |
| POST   | /run/stop                                 | Cancel running backup              |
| POST   | /verify                                   | Verify backup integrity            |
| GET    | /runs                                     | Backup history                     |
| GET    | /runs/:id                                 | Single run detail                  |
| GET    | /runs/:id/logs                            | Run log entries                    |
| POST   | /restore                                  | Restore files                      |
| GET    | /config                                   | Current configuration              |
| PATCH  | /config                                   | Update configuration               |
| GET    | /config/audit                             | Configuration audit trail          |
| POST   | /config/sites                             | Add backup source folder           |
| PATCH  | /config/sites/:name                       | Update source folder settings      |
| DELETE | /config/sites/:name                       | Remove backup source folder        |
| GET    | /ssd/status                               | SSD health and disk usage          |
| GET    | /alerts                                   | In-app alert list                  |
| POST   | /alerts/:id/dismiss                       | Dismiss alert                      |
| POST   | /alerts/dismiss-all                       | Dismiss all alerts                 |
| PATCH  | /settings/smtp                            | Update SMTP settings               |
| POST   | /settings/smtp/test                       | Send test email                    |
| PATCH  | /settings/retention                       | Update retention policy            |
| POST   | /settings/prune                           | Run prune job                      |
| POST   | /settings/encryption/generate-key         | Generate new encryption key         |
| GET    | /watcher/status                           | File watcher status                |
| POST   | /watcher/start                            | Start file watcher                 |
| POST   | /watcher/stop                             | Stop file watcher                  |

---

# ⚙️ Configuration

Configuration file location:

```
backend/config/config.yaml
```

Copy template from:

```
backend/config/config.yaml.example
```

Example configuration:

```yaml
ssd_path: "D:\\GhostBackup"
secondary_ssd_path: "E:\\GhostBackup2"   # optional, leave empty to disable

encryption:
  enabled: true   # requires GHOSTBACKUP_ENCRYPTION_KEY in .env.local

sources:
  - label: "Client Records"
    path: "C:\\Users\\admin\\SharePoint\\Red Parrot\\Clients"
    enabled: true

retention:
  daily_days: 365
  weekly_days: 2555
  compliance_years: 7
  guard_days: 7

schedule:
  time: "08:00"
  timezone: "Europe/London"

circuit_breaker_threshold: 0.05
```

---

# 🔑 Environment Variables

```bash
export GHOSTBACKUP_ENCRYPTION_KEY="your-fernet-key"
export GHOSTBACKUP_SMTP_PASSWORD="your-password"
export GHOSTBACKUP_API_PORT="8765"
```

`GHOSTBACKUP_API_TOKEN` is automatically generated by Electron.
`GHOSTBACKUP_API_PORT` is optional and defaults to `8765`. Electron passes the active port to the backend and exposes the matching runtime API URL to the renderer, so desktop UI requests follow the configured port end-to-end.

---

# 📂 Project Structure

```
GhostBackup/
│
├── install.bat              ← run this first on a new machine
├── start.bat                ← created by installer, launches the app
│
├── backend/
│   ├── config/
│   │   ├── config.yaml.example
│   │   └── config.yaml
│   ├── api.py               ← FastAPI server (default port 8765)
│   ├── config.py            ← ConfigManager
│   ├── manifest.py          ← SQLite run/file/audit database
│   ├── reporter.py          ← AlertManager + SMTP email
│   ├── scheduler.py         ← APScheduler daily job + watchdog
│   ├── setup_helper.py      ← called by install.bat
│   ├── syncer.py            ← file scan, encrypt, copy, verify, prune
│   ├── utils.py             ← shared fmt_bytes / fmt_duration helpers
│   ├── watcher.py           ← watchdog real-time file watcher
│   └── tests/
│       ├── conftest.py
│       ├── test_api.py
│       ├── test_config.py
│       ├── test_crypto.py
│       ├── test_manifest.py
│       ├── test_reporter.py
│       ├── test_scheduler_utils.py
│       ├── test_setup_helper.py
│       ├── test_syncer_copy.py
│       ├── test_syncer_restore.py
│       ├── test_syncer_scan.py
│       ├── test_syncer_utils.py
│       ├── test_syncer_verify.py
│       ├── test_watcher.py
│       └── test_utils.py
│
├── electron/
│   ├── main.js              ← main process, spawns backend, tray
│   └── preload.js           ← contextBridge API surface
│
├── src/
│   ├── GhostBackup.jsx      ← app shell + navigation
│   ├── main.jsx             ← React entry point + backend poller
│   ├── api-client.js        ← authenticated fetch wrapper
│   ├── styles.css           ← all app styles
│   ├── splash.css           ← splash screen styles
│   ├── components/          ← reusable UI components
│   │   ├── AlertBell.jsx
│   │   ├── Countdown.jsx
│   │   ├── ErrBanner.jsx
│   │   ├── Heatmap.jsx
│   │   ├── LoadingState.jsx
│   │   ├── SsdGauge.jsx
│   │   └── StatusPill.jsx
│   ├── pages/               ← full-page views
│   │   ├── BackupConfig.jsx
│   │   ├── Dashboard.jsx
│   │   ├── LiveRun.jsx
│   │   ├── LogsViewer.jsx
│   │   ├── RestoreUI.jsx
│   │   └── Settings.jsx
│   └── tests/
│       ├── api-client.test.js
│       ├── backup-config.test.jsx
│       ├── components.test.jsx
│       └── setup.js
│
└── SETUP.md
```

---

# 🔐 Security

| Layer              | Implementation                                        |
| ------------------ | ----------------------------------------------------- |
| Encryption         | AES-256-GCM streaming with version header (key rotation ready) |
| API Authentication | Timing-safe session API tokens (`hmac.compare_digest`) |
| Path Safety        | Path traversal validation on restore endpoint          |
| Electron Sandbox   | Chromium sandbox enabled, CSP in dev + production      |
| Credential Safety  | Input sanitization on credential writes                |
| Database Safety    | SQLite with `PRAGMA synchronous=FULL`, batched commits |
| Process Safety     | Process name verification before termination           |
| Data Integrity     | xxhash verification                                    |
| Failure Control    | Circuit breaker threshold                              |

---

# 📜 Compliance

GhostBackup supports long-term data retention requirements.

| Policy           | Value                        |
| ---------------- | ---------------------------- |
| Daily retention  | 365 days                     |
| Weekly retention | 2555 days                    |
| Audit trail      | Configuration changes logged |
| Integrity check  | `/verify` endpoint           |

---

# 💼 Use Cases

GhostBackup is suitable for:

• Accounting firms
• Legal offices
• Financial services
• Medical record systems
• Businesses requiring secure automated backups

---

# 👨‍💻 Author

**Egyan07**

Built for **RedParrot Accounting**.

---

# 📄 License

MIT License

---

# 📋 Changelog

## v2.3.0 — Security Hardening, Performance & Test Coverage

### Critical Security Fixes
- **Timing-safe API token comparison** (`api.py`): replaced plain `!=` string comparison with `hmac.compare_digest()` to prevent timing-based side-channel attacks.
- **Path traversal validation** (`api.py`, `syncer.py`): restore endpoint now validates destination path and blocks `..` path segments. Both API layer and syncer enforce this as defence-in-depth.
- **Encryption key versioning** (`syncer.py`): encrypted files now include a version byte (`_ENCRYPTION_VERSION = 0x01`) in the header, enabling future key rotation without breaking old backups. Critical for 7-year compliance retention.
- **Electron `shell:open-path` validation** (`main.js`): IPC handler now validates the path exists and is a directory before opening, preventing arbitrary file/executable execution from a compromised renderer.
- **Credential injection prevention** (`main.js`): values written to `.env.local` are sanitized — newline, carriage return, double quote, and backslash characters are rejected.
- **Notification server body limit** (`main.js`): HTTP notification server on port 8766 now caps request body at 10KB to prevent memory exhaustion from local processes.
- **Dependencies updated**: `cryptography` 42.0.5 → 44.0.0, `fastapi` 0.111.0 → 0.115.0, `electron` 31.0.0 → 33.3.1. All carry known CVE patches.
- **CI security auditing** (`ci.yml`): added `pip-audit` and `npm audit` job to catch vulnerable dependencies automatically.

### Important Fixes
- **Race condition eliminated** (`api.py`): `/run/start` and `/run/stop` now acquire `_run_mutex` before checking or mutating `_active_run`, preventing duplicate concurrent runs.
- **SQLite batch commits** (`manifest.py`): removed per-record `commit()` calls from `record_file()` and `log()`. Added `flush()` method called after each library scan — major performance improvement for large backups (thousands of files).
- **Chromium sandbox enabled** (`main.js`): `sandbox: true` in BrowserWindow reduces attack surface.
- **Production CSP headers** (`main.js`): Content-Security-Policy now set for both dev and production builds.
- **Config encapsulation** (`config.py`, `syncer.py`): added `encryption_config_enabled` property — syncer no longer accesses `config._data` directly.
- **SMTP key whitelisting** (`config.py`): `update_smtp()` uses an explicit key allowlist instead of only filtering password.
- **Query parameter bounds** (`api.py`): `limit` capped at 1000, `offset` minimum 0 on `/runs` and `/config/audit` endpoints.
- **Mount point matching** (`syncer.py`): replaced string `startswith()` with `Path.is_relative_to()` to prevent false matches.
- **Async desktop notify** (`api.py`): wrapped blocking `http.client` call in `asyncio.to_thread()` so it no longer blocks the event loop.
- **LiveRun polling fix** (`LiveRun.jsx`): replaced `setInterval` with `useRef`-based `setTimeout` that adjusts delay without recreating the interval on every status change.
- **ESLint restored in CI** (`ci.yml`): lint job now runs `npm run lint`.
- **CI syntax check** (`ci.yml`): replaced hardcoded file list with `python -m compileall backend/ -q`.

### Minor Fixes
- **Timezone consistency** (`watcher.py`): `datetime.now()` → `datetime.now(timezone.utc)`.
- **UTC string handling** (`LiveRun.jsx`): normalizes Python's `+00:00` suffix to `Z` before parsing.
- **Memory leak fix** (`LogsViewer.jsx`): `URL.revokeObjectURL()` called after CSV export.
- **Dynamic version chip** (`GhostBackup.jsx`): fetches version from IPC instead of hardcoded `v2.0.0`.
- **Duplicate exclusion check** (`BackupConfig.jsx`): prevents adding duplicate patterns.
- **Platform-aware restore path** (`RestoreUI.jsx`): defaults to Linux path on non-Windows.
- **Error logging** (`AlertBell.jsx`): empty `catch {}` blocks now log via `console.warn`.
- **Keyboard accessibility** (`GhostBackup.jsx`): nav items have `role="button"`, `tabIndex`, `onKeyDown`.
- **Install safety** (`install.bat`): won't overwrite existing `start.bat`.
- **Coverage threshold** (`ci.yml`): raised from 60% to 70%.
- **Node 22 LTS** (`ci.yml`): added to frontend test matrix.
- **SETUP.md clarification**: noted Fernet key format vs AES-256-GCM encryption.
- **Test dependencies pinned** (`requirements.txt`): `pytest==8.3.4`, `httpx==0.27.2` (were unpinned with `>=`).

### New Tests (21 tests across 4 new files)

| File | Tests | Coverage |
|------|-------|----------|
| `test_syncer_copy.py` | 6 | `copy_file()`: basic, atomic write, checksum, dirs, encryption, secondary SSD |
| `test_syncer_restore.py` | 5 | `restore_files()`: basic, decryption round-trip, path traversal blocked, dirs, missing file |
| `test_syncer_verify.py` | 3 | `verify_backups()`: intact, corrupted, missing |
| `test_watcher.py` | 5 | `_SourceHandler`: debounce, cooldown, UTC timezone, ghosttmp ignored, exclusions |
| `test_manifest.py` | +1 | `flush()` batch commit verification |

---

## v2.1.0 — Security Fixes, Streaming Encryption & Production Hardening

### Critical Fixes
- **Streaming AES-256-GCM encryption** (`syncer.py`): replaced Fernet's whole-file-in-memory encryption with chunked AES-256-GCM streaming — memory usage is now constant regardless of file size. Legacy Fernet-encrypted backups are auto-detected and decrypted transparently.
- **Thread-safe `_active_run` mutations** (`api.py`): added `threading.Lock` around all compound operations (`+=`, `.append()`, multi-field updates) on the shared run state dict, eliminating data races between the progress callback (executor thread) and the event loop thread.

### Important Fixes
- **`datetime.utcnow()` replaced** (`manifest.py`, `api.py`, `syncer.py`): all deprecated `datetime.utcnow()` calls replaced with `datetime.now(timezone.utc)` for Python 3.12+ compatibility and correct timezone handling.
- **CI lint job fixed** (`ci.yml`): removed duplicate flake8 step, restored ESLint for JavaScript linting.
- **Secondary SSD infinite-recursion guard** (`syncer.py`): added `_skip_secondary` parameter to `copy_file()` to prevent recursive secondary copy from triggering another secondary copy.
- **Notification server authenticated** (`main.js`, `api.py`): the HTTP notification server on port 8766 now validates the `X-API-Key` header — only the backend can trigger desktop notifications.
- **`ThreadPoolExecutor` shutdown** (`api.py`): changed from `shutdown(wait=False)` to `shutdown(wait=True, cancel_futures=True)` so in-flight copies are cancelled promptly on abort.
- **Version strings aligned** (`api.py`, `package.json`): all version references now consistently report `2.0.0`.
- **CORS `"null"` origin removed** (`api.py`): removed unnecessary `"null"` from allowed CORS origins.

### Minor Fixes
- **`schema_version` table populated** (`manifest.py`): the migration now inserts an initial schema version for future upgrade detection.
- **Retention UI max corrected** (`Settings.jsx`): `weekly_days` input max raised from 1825 to 3650 to accommodate the 7-year (2555-day) compliance default.
- **Electron-builder config paths fixed** (`package.json`): `config/**/*` updated to `backend/config/**/*` since the root `config/` directory was removed in v2.0.0.
- **Duplicate LIKE escaping consolidated** (`manifest.py`): `clear_file_hashes` now uses the shared `_escape_like()` helper instead of reimplementing the same logic.
- **"Start with Windows" hidden on non-Windows** (`main.js`): the tray menu item is now only shown on Windows.
- **Adaptive LiveRun polling** (`LiveRun.jsx`): polls every 1s during active runs, every 5s when idle (saves battery on laptops).
- **Encryption description updated** (`Settings.jsx`): UI now correctly states "AES-256-GCM streaming" instead of "AES-128 (Fernet)".

---

## v2.0.0 — Architecture Overhaul, Security Hardening & Full Test Suite

### Security
- **CSP hardened**: removed `unsafe-inline` from `script-src` in `index.html` — all inline style injection replaced with static CSS imports
- **`asyncio.Lock` on backup guard**: `_active_run` check-and-set in `api.py` is now atomic, eliminating the race condition where two concurrent triggers could start duplicate backup runs
- **Encryption key rotation UI**: new `POST /settings/encryption/generate-key` endpoint and Settings panel card with a confirmation modal — key is generated server-side, displayed once for the user to save, and never persisted by the backend

### Frontend — Component Architecture
- **`src/GhostBackup.jsx`** rewritten from 2134 lines to ~110 lines — all UI extracted into purpose-built files:
  - `src/pages/`: `Dashboard`, `LiveRun`, `LogsViewer`, `BackupConfig`, `RestoreUI`, `Settings`
  - `src/components/`: `StatusPill`, `SsdGauge`, `Heatmap`, `Countdown`, `ErrBanner`, `LoadingState`, `AlertBell`
- **`src/main.jsx`**: removed inline `<style>` injection; imports `splash.css` and `styles.css` as static files
- **`src/styles.css`** and **`src/splash.css`**: all 600+ lines of CSS extracted from JSX template literals
- **`src/api-client.js`**: added `generateEncryptionKey()` method

### Backend — Bug Fixes
- **`version_count` removed from API surface** (`api.py`, `config.py`, `BackupConfig.jsx`): the setting was accepted and stored but silently had no effect on the pruner — exposing it was misleading. Removed until the pruner enforces it.
- **`setup_helper.py`**: YAML config patching replaced from fragile string-replace to proper `yaml.safe_load` → mutate → `yaml.dump`. Windows backslash paths, quoted values, and any future format changes are handled correctly. Added duplicate-source guard.
- **`utils.py`** (new): shared `fmt_bytes` / `fmt_duration` helpers extracted from `manifest.py` and `reporter.py` where they were duplicated verbatim.

### Dependencies
- **`package.json`**: all `^` version prefixes removed — exact pins across all 10 packages for reproducible installs
- Added `@testing-library/react 15.0.7` and `@testing-library/user-event 14.5.2` as pinned devDependencies
- **`vite.config.js`**: fixed test `include` path (was doubled under `root: "src"`), added `setupFiles` for `@testing-library/react` cleanup

### Tests — Full Coverage Added
**Backend (214 pytest tests across 10 files):**

| File | Tests |
|------|-------|
| `test_utils.py` | 20 — `fmt_bytes` / `fmt_duration` boundaries |
| `test_reporter.py` | 25 — `Alert`, `AlertManager`, `Reporter.send_run_report` |
| `test_crypto.py` | 12 — encrypt/decrypt round-trip, wrong-key rejection, no-op mode |
| `test_syncer_scan.py` | 18 — `scan_source`: exclusions, incremental cache, force_full, size guard |
| `test_setup_helper.py` | 8 — YAML parse→mutate→dump, duplicate guard, Windows paths |
| `test_api.py` | +5 — `TestEncryptionKey` class added to existing suite |
| `test_manifest.py` | Fixed broken import after `_fmt_bytes`/`_fmt_duration` moved to `utils.py` |

**Frontend (60 vitest tests across 3 files):**

| File | Tests |
|------|-------|
| `api-client.test.js` | +1 — `generateEncryptionKey` method |
| `components.test.jsx` | 29 — `ErrBanner`, `StatusPill` (all statuses), `LoadingState`, `Countdown` |

---

## v1.3.0 — Frontend API Client Fixes

**src/api-client.js** *(fixed)*
- Added `export default api` — `GhostBackup.jsx` imports the default export; the missing default export would have caused every API call to throw at runtime
- Added 20 named convenience methods (`health`, `dashboard`, `startRun`, `stopRun`, `runStatus`, `getRuns`, `getRun`, `getRunLogs`, `restore`, `getConfig`, `updateConfig`, `addSite`, `removeSite`, `updateSmtp`, `testSmtp`, `updateRetention`, `runPrune`, `ssdStatus`, `getAlerts`, `dismissAlert`, `dismissAllAlerts`, `watcherStatus`, `watcherStart`, `watcherStop`) — all calls from `GhostBackup.jsx` now resolve to correct endpoints

**src/GhostBackup.jsx** *(fixed)*
- Replaced 6 raw `fetch("http://127.0.0.1:8765/...")` calls with the authenticated `api.*()` wrapper — these calls bypassed the `X-API-Key` header and would have returned 401 for any token-protected deployment:
  - `SsdDriveStatus` component: `fetch(/ssd/status)` → `api.ssdStatus()`
  - Settings panel `useEffect` + `refreshSsd()`: two `fetch(/ssd/status)` → `api.ssdStatus()`
  - `AlertBell.fetchAlerts()`: `fetch(/alerts)` → `api.getAlerts()`
  - `AlertBell.dismiss()`: `fetch(/alerts/:id/dismiss)` → `api.dismissAlert(id)`
  - `AlertBell.dismissAll()`: `fetch(/alerts/dismiss-all)` → `api.dismissAllAlerts()`

**src/tests/api-client.test.js** *(updated)*
- Added 16 new tests for the named API methods and for the `export default` identity check
- Total frontend test count: 38 tests

---

## v1.2.0 — Automated Installer & Test Coverage

**install.bat** *(new)*
- One-step Windows installer: checks Python 3.10+ and Node 18+, creates `.venv`, installs all dependencies, then calls `setup_helper.py`
- Creates `start.bat` as a one-click launcher after setup completes

**backend/setup_helper.py** *(new)*
- Interactive setup: asks for source folder, primary SSD path, and optional secondary SSD path
- Generates a Fernet encryption key, saves it to `.env.local`, and displays it prominently on screen with instructions to store it on a separate device
- Patches `config.yaml` in place with the entered paths so the app is ready to run immediately

**backend/tests/test_api.py** *(new)*
- 30 FastAPI endpoint tests covering `/health`, auth middleware, `/run/start`, `/run/stop`, `/run/status`, `/runs`, `/config`, `/restore`, `/alerts`, `/settings/retention`, `/verify`, `/watcher`
- All backend services mocked — tests run without a real SSD, scheduler, or file watcher

**src/tests/api-client.test.js** *(new)*
- 22 Vitest unit tests for `api-client.js` covering `ApiError`, `request()`, token caching, query string handling, error propagation, and the `api` convenience wrapper
- Runs in jsdom — no browser or Electron required

**package.json / vite.config.js**
- Added `vitest` and `jsdom` dev dependencies
- Added `npm test` and `npm run test:watch` scripts
- Added `test` block to `vite.config.js` pointing at `src/tests/`

---

## v1.1.0 — Code Quality & Bug Fixes

**backend/api.py**
- Moved inline imports (`shutil`, `http.client`, `json`, `pathlib.Path`) to module level
- Replaced deprecated `asyncio.get_event_loop()` with `asyncio.get_running_loop()` (Python 3.10+)
- Extracted `_desktop_notify()`, `_new_run_state()`, `_retry_locked_files()`, and `_backup_manifest_to_ssd()` out of `run_backup_job` to reduce function length
- Fixed private method access: replaced `syncer._hash_file_direct()` with `syncer.hash_file()`
- Wrapped `executor.shutdown()` in `try/finally` to guarantee cleanup on error

**backend/manifest.py**
- Fixed thread-safety bug: added missing `with self._lock:` guard in `get_backup_files_for_prune()`
- Added `get_latest_backed_up_files_for_source()` public method — callers no longer access `._conn` directly
- Added `_escape_like()` helper to correctly escape `%` and `_` in SQLite LIKE queries
- Moved `import socket` from inside `log_config_change()` to module level

**backend/syncer.py**
- Renamed `_hash_file_direct()` → `hash_file()` to correctly reflect its public usage
- `verify_backups()` now uses the new manifest public method instead of accessing `._conn` directly
- Added `_LARGE_FILE_WARN_BYTES` constant (200 MB) with a log warning when Fernet loads a large file into memory

**backend/watcher.py**
- Split `_last_triggered` into `_last_triggered_mono` (monotonic, for cooldown arithmetic) and `_last_triggered_at` (datetime, for display) — eliminated fragile mixed-clock calculation
- `status()` now returns a correctly formatted timestamp string

**backend/config.py**
- Removed duplicate `SourceConfig.circuit_breaker_threshold` field — threshold is defined at global config level only
- Moved `_deep_merge` to a module-level function (was a static method that inconsistently both mutated and returned `base`)
- `remove_site()` simplified using `next()` with a default
- `add_site()` error messages now state exactly which field is missing
- Fixed side-effect bug in `update_smtp()` — no longer mutates the caller's dict via `.pop()`

**backend/reporter.py**
- Fixed thread-safety bug: `Alert._id_counter` now incremented under `_alert_id_lock` via `_next_alert_id()`
- Fixed `REPORT_DIR` from `Path("reports")` (CWD-relative) to `Path(__file__).parent / "reports"` (anchored to module location)
- Added proper type annotation for `_notify_callback`: `Optional[Callable[[str, str], Coroutine]]`
- Extracted `_LEVEL_COLOURS` and `_LEVEL_ICONS` as module-level constants

**backend/scheduler.py**
- Replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` (Python 3.12+)
- Made `_job_start_time` timezone-aware
- Moved `from datetime import timezone` out of an inner function into module-level imports
- Extracted `_parse_time()` to module level for testability
- Renamed `_watchdog_alerted` → `_stall_alerted` for clarity

**electron/main.js**
- Removed `Atomics.wait(...)` call that was synchronously blocking the Electron main thread for 300 ms on every startup
- Replaced with an async `sleep()` helper using `setTimeout`

**src/api-client.js**
- Set `ApiError.name = "ApiError"` to fix `instanceof` checks across module boundaries
- Added `clearTokenCache()` export for use in tests
- Added JSDoc parameter and return types to `request()`

**backend/tests/** *(new)*
- Added pytest test suite: `test_manifest.py` (25 tests), `test_config.py` (34 tests), `test_syncer_utils.py` (18 tests), `test_scheduler_utils.py`
- Added `conftest.py` to configure `sys.path` for all test modules

---

# 👻 GhostBackup

**Silent. Secure. Compliant.**
