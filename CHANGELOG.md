# 📋 Changelog

All notable changes to GhostBackup are documented here.

---

## v2.9.0 — Desktop Notifications, CSV Audit Log, Dark/Light Theme & CI Coverage

### Notifications
- **Desktop toast on backup completion** (`reporter.py`): success runs now fire a Windows desktop notification via the Electron notify server — all three outcomes (success, partial, failed) now show a toast

### Frontend
- **Dark/light theme toggle** (`GhostBackup.jsx`, `styles.css`): ☀️/🌙 button in the topbar; choice persists via `localStorage`
- **Export audit log as CSV** (`api.py`, `api-client.js`, `LogsViewer.jsx`): `GET /runs/export` endpoint returns all run history as a downloadable CSV; Export CSV button added to the Logs page Run History panel
- **ESLint globals fix** (`eslint.config.js`): added `localStorage` to browser globals

### CI / Tooling
- **Frontend coverage** (`vite.config.js`, `package.json`, `ci.yml`): `npm run test:coverage` generates v8 coverage report; CI runs coverage on Node 20 — baseline **62.54%** statements
- `@vitest/coverage-v8@1.6.1` added as dev dependency

### Testing
- **338 backend + 134 frontend = 472 tests**, all passing

---

## v2.8.0 — Dashboard & Restore Frontend Tests

### Testing
- **`dashboard.test.jsx`** (35 tests): loading state, error state, stat strip, active run banner, run history/heatmap, next scheduled run countdown, SSD storage, folder status table, auto-refresh interval
- **`restore.test.jsx`** (31 tests): loading state, error state, run list (failed run filtering), library selection, destination path, dry-run toggle, restore button, restore result panel, warning banner
- Frontend total: **60 → 134 tests** across 6 test files, all passing
- **Total: 338 backend + 134 frontend = 472 tests passing**

---

## v2.7.0 — WAL Checkpoint, Key Fingerprint Tracking & Backup Job Integration Tests

### Reliability
- **WAL checkpoint after every run** (`manifest.py`): `finalize_run()` now calls `PRAGMA wal_checkpoint(PASSIVE)` after each run commit — prevents unbounded WAL file growth on long-running installations

### Security
- **Encryption key fingerprint tracking** (`syncer.py`, `manifest.py`, `api.py`): Each backed-up file now stores a 16-hex-char SHA-256 fingerprint of the derived AES key in the `key_fingerprint` column (schema v3). On restore, if the stored fingerprint doesn't match the current key, a warning is logged before decryption — detects key rotation without re-encryption of historical backups
- `_CryptoHelper.key_fingerprint` property — first 16 hex chars of SHA-256 of the 32-byte AES key, safe to store in the DB
- `LocalSyncer.key_fingerprint` property — exposes crypto fingerprint as a public property

### Testing
- **11 integration tests for `run_backup_job`** (`test_backup_job.py`): covers success path (no files, with files, skipped count, full backup flag), failure paths (SSD not ready, no sources, copy failure, already running, missing source folder), and source filtering
- `api.py` coverage: 66% → **81%**
- **Total: 325 → 338 backend tests passing, 88% → 90% overall coverage**

---

## v2.6.0 — Security Hardening, Reliability & Architecture Completion

### Security
- **Per-installation HKDF salt** (`config.py`, `syncer.py`): `GHOSTBACKUP_HKDF_SALT` env var replaces the hardcoded static salt used to derive the AES-256-GCM key from the Fernet key material. Falls back to the static default for backward compatibility with existing encrypted backups. Existing installs are unaffected; new installs should set this on first launch.
- `electron/main.js`: `GHOSTBACKUP_HKDF_SALT` added to `ALLOWED_KEYS` and `credentials:status`

### Reliability
- **`.ghosttmp` orphan cleanup** (`syncer.py`): `LocalSyncer.__init__` now scans the SSD for leftover `.ghosttmp` files from interrupted runs and removes them at startup
- **`record_file()` periodic commit** (`manifest.py`): file records are committed to SQLite every 100 inserts — reduces crash data loss window from the entire run to the last 100 files

### Architecture
- **`run_backup_job` fully injected** (`api.py`): all `_config`, `_manifest`, `_reporter`, `_syncer`, `_scheduler` globals replaced with injected parameters throughout the backup job body. Falls back to module globals when called from the scheduler or watcher (which cannot use `Depends()`)
- **`PATCH /config` returns `ignored_keys`** (`config.py`, `api.py`): unknown keys in a config update are now surfaced in the response instead of being silently dropped
- **Real schema migration** (`manifest.py`): `_migrate()` now reads the current `schema_version`, applies numbered delta migrations in order, and commits each step atomically. `_SCHEMA_VERSION = 2` adds `library_summary` column via `ALTER TABLE`

### Frontend
- **Visibility-aware alert polling** (`AlertBell.jsx`): the 15s alert poll is skipped when `document.visibilityState !== 'visible'` — eliminates background API calls when the window is hidden

### Testing
- 6 new tests: `update()` `ignored_keys`, `hkdf_salt` default + env override, schema version on fresh DB, migration idempotency, `db_path` property
- **Total: 319 → 325 backend tests passing**

---

## v2.5.3 — Public API Completion, Test Expansion & Bug Fix

### Backend — Encapsulation
- **`LocalSyncer.encryption_active` property** — replaces direct `_crypto.enabled` access from `api.py`
- **`ManifestDB.db_path` property** — replaces direct `_path` access from `api.py`

### Backend — Bug Fix
- **`generate_health_report` crash fixed** — `_HEALTH_REPORT_TEMPLATE` used `.format()` on a string containing CSS curly braces, raising `KeyError` on every health report generation. Replaced with `.replace()` calls.

### Testing
- 10 new `BackupScheduler` tests — lifecycle, retry logic, `reset_missed_alert`. Coverage: 28% → 70%
- 9 new `Reporter` tests — `_send_email`, `send_test_email`, `generate_health_report`. Coverage: 56% → 71%
- **Total: 300 → 319 backend tests, 85% → 88% overall coverage**

---

## v2.5.2 — Exception Specificity & Test Coverage Expansion

### Backend
- **Exception specificity in `syncer.py`** — `restore_files` and `verify_backups` broad `except Exception` blocks narrowed to `(PermissionError, OSError, RuntimeError)`

### Testing
- 8 new `FileWatcher` unit tests — lifecycle: start, stop, reload, idempotency, dispatch safety. `watcher.py` coverage: 56% → 92%
- 7 new API endpoint tests — watcher start/stop, prune, dashboard, SSD status
- **Total: 285 → 300 tests, 83% → 85% coverage**

---

## v2.5.1 — Config Schema Validation

### Backend
- **Input validation on `ConfigManager.update()`** — validates `schedule_time` (HH:MM), `timezone` (IANA), `concurrency` (1–32), `max_file_size_gb` (1–100), `circuit_breaker_threshold` (0.0–1.0), `exclude_patterns` (list of strings). Invalid values raise `ValueError` → HTTP 400.
- 7 new validation tests in `test_config.py`. **Total: 278 → 285 tests**

---

## v2.5.0 — Complete Dependency Injection

### Backend
- **Full DI coverage** — all 25 remaining endpoints now declare dependencies via `Depends()` instead of module globals
- **`/health` version fix** — version string now reads from `app.version` dynamically instead of hardcoded `"2.3.2"`
- **`_do_prune` fully injected** — config, syncer, and reporter passed through from endpoint into background task

---

## v2.4.3 — Internal API Hardening & Zero Lint Warnings

### Backend
- **`FileWatcher.is_running` property** — replaces direct `_running` attribute access
- **`BackupScheduler.reset_missed_alert()`** — public method replaces direct `_missed_alerted` mutation
- **`manifest.log()` commits immediately** — log entries no longer at risk of loss on crash

### Frontend / Tooling
- **Zero ESLint warnings** — `no-unused-vars` rule ignores PascalCase (JSX components)

---

## v2.4.2 — Remove Dead Lock, Wire DI into Endpoint Bodies, Log Notify Failures

### Backend
- **`_active_run_lock` dead code removed** — unified to single `_run_mutex` threading.Lock
- **DI completed in endpoint bodies** — `restore`, `verify`, `smtp/test` endpoints use injected deps
- **Silent failure fixed** — `_desktop_notify` errors now logged at DEBUG level

---

## v2.4.1 — Fix get_config Name Collision, Unify Run Lock, Manifest Close Race

### Backend
- **`get_config` name collision fixed** — dep provider renamed to `provide_config`
- **Dual-lock unified** — `run_backup_job` uses `_run_mutex` throughout
- **`manifest.close()` race fixed** — `_conn.close()` moved inside lock

---

## v2.4.0 — Phase 1 Polish

### Frontend
- **React Error Boundary** (`src/components/ErrorBoundary.jsx`, `src/main.jsx`): class component catches uncaught render errors and shows a recoverable "Something went wrong" screen instead of a blank white page.
- **CSS class extraction** (`src/styles.css`): modal overlay/box/title, key-display, stat-card, and ssd-status-card styles extracted into named classes.

### Backend
- **Rate limiting** (`backend/api.py`, `backend/requirements.txt`): slowapi rate limits on 5 sensitive endpoints — `/run/start` (10/min), `/restore` (5/min), `/verify` (5/min), `/settings/smtp/test` (3/min), `/settings/encryption/generate-key` (5/min).
- **FastAPI dependency providers** (`backend/api.py`): `get_config()`, `get_manifest()`, `get_scheduler()`, `get_reporter()`, `get_syncer()`, `get_watcher()` wired into rate-limited endpoints via `Depends()`.

---

## v2.3.2 — Code Review & Reliability Hardening

### Backend
- **Configurable watcher timings** (`config.yaml`, `watcher.py`): `debounce_seconds` and `cooldown_seconds` are now read from `config.yaml` under a `watcher:` block (defaults: 15s / 120s) instead of being hardcoded constants.
- **asyncio.Lock lifespan fix** (`api.py`): `asyncio.Lock()` is now created inside the FastAPI lifespan context rather than at module import time, preventing "attached to a different event loop" errors on Python 3.10+.
- **`GHOSTBACKUP_DB_PATH` env override** (`manifest.py`): the SQLite database path can now be overridden via the `GHOSTBACKUP_DB_PATH` environment variable, making standalone backend runs outside the project directory simpler.
- **Reporter template fix** (`reporter.py`): resolved a Jinja2 template rendering edge case that produced malformed HTML in email reports when folder summary data was absent.
- **`os` import added** (`manifest.py`): missing `import os` added to support the `GHOSTBACKUP_DB_PATH` env var lookup without a `NameError` at startup.

### Frontend & Electron
- **Dynamic app version in sidebar** (`electron/main.js`, `electron/preload.js`, `src/GhostBackup.jsx`): the sidebar now reads version and author from `package.json` via contextBridge IPC instead of hardcoding them, so version bumps automatically appear in the UI.

### CI / Tooling
- **`npm ci` in CI** (`.github/workflows/ci.yml`): replaced `npm install` with `npm ci` for reproducible, lockfile-exact dependency installs in all CI runs.
- **Test debounce speed-up** (`backend/tests/test_watcher.py`): watcher debounce test now uses `debounce_seconds=0.1` so the suite runs in milliseconds rather than waiting the full 15s default.

### Repository
- **`.gitignore` cleanup**: removed stale artifact patterns that were no longer generated by the build.

---

## v2.3.1 — Post-Release Patch

### Bug Fixes
- **Sidebar layout fix** (`splash.css`, `GhostBackup.jsx`): splash screen `body` styles were bleeding into the main app layout, causing the sidebar to expand and collapse unpredictably across pages. Splash styles are now scoped to a `body.splash-active` class that is removed once the app is ready.
- **Port cleanup on quit** (`main.js`): closing the app via File → Exit or tray → Quit now kills any process still holding port 8765, preventing "port already in use" errors on next launch.
- **`wmic` replaced with `tasklist`** (`main.js`): `wmic` is deprecated and unavailable on some Windows 11 configurations. Port conflict detection now uses `tasklist /FI "PID eq <pid>"` which works on all supported Windows versions.

### Dependency & Tooling
- **`cryptography` pinned to 44.0.2**: `msal` (Microsoft SharePoint auth) requires `cryptography<45`. CVE-2026-26007 and CVE-2026-34073 are acknowledged and suppressed in CI via `pip-audit --ignore-vuln` until `msal` relaxes its constraint.
- **ESLint v9 flat config migration** (`eslint.config.js`): migrated from legacy `.eslintrc` to `eslint.config.js` flat config format required by ESLint v9. Added browser and Node globals to fix false-positive `no-undef` errors in CI.

### Repository Hygiene
- **`start.bat` removed from repo**: this file is generated by `install.bat` with machine-specific paths and should never be committed. Added to `.gitignore`.

---

## v2.3.0 — Security Hardening, Performance & Test Coverage

### Critical Security Fixes
- **Timing-safe API token comparison** (`api.py`): replaced plain `!=` string comparison with `hmac.compare_digest()` to prevent timing-based side-channel attacks.
- **Path traversal validation** (`api.py`, `syncer.py`): restore endpoint now validates destination path and blocks `..` path segments. Both API layer and syncer enforce this as defence-in-depth.
- **Encryption key versioning** (`syncer.py`): encrypted files now include a version byte (`_ENCRYPTION_VERSION = 0x01`) in the header, enabling future key rotation without breaking old backups. Critical for 7-year compliance retention.
- **Electron `shell:open-path` validation** (`main.js`): IPC handler now validates the path exists and is a directory before opening, preventing arbitrary file/executable execution from a compromised renderer.
- **Credential injection prevention** (`main.js`): values written to `.env.local` are sanitized — newline, carriage return, double quote, and backslash characters are rejected.
- **Notification server body limit** (`main.js`): HTTP notification server on port 8766 now caps request body at 10KB to prevent memory exhaustion from local processes.
- **Dependencies updated**: `cryptography` 42.0.5 → 46.0.5, `fastapi` 0.111.0 → 0.135.2, `pydantic` 2.7.0 → 2.12.5, `uvicorn` 0.29.0 → 0.34.0, `python-multipart` 0.0.9 → 0.0.22, `PyYAML` 6.0.1 → 6.0.2, `xxhash` 3.4.1 → 3.5.0, `electron` 31.0.0 → 33.3.1.
- **`package-lock.json` synced**: regenerated to match `package.json` — fixes `npm ci` failures in CI.
- **CI security auditing** (`ci.yml`): added `pip-audit` and `npm audit` job to catch vulnerable dependencies automatically.

### Important Fixes
- **Race condition eliminated** (`api.py`): `/run/start` and `/run/stop` now acquire `_run_mutex` before checking or mutating `_active_run`, preventing duplicate concurrent runs.
- **SQLite batch commits** (`manifest.py`): removed per-record `commit()` calls from `record_file()` and `log()`. Added `flush()` method called after each library scan — major performance improvement for large backups.
- **Chromium sandbox enabled** (`main.js`): `sandbox: true` in BrowserWindow reduces attack surface.
- **Production CSP headers** (`main.js`): Content-Security-Policy now set for both dev and production builds.
- **Config encapsulation** (`config.py`, `syncer.py`): added `encryption_config_enabled` property.
- **SMTP key whitelisting** (`config.py`): `update_smtp()` uses an explicit key allowlist.
- **Query parameter bounds** (`api.py`): `limit` capped at 1000, `offset` minimum 0.
- **Mount point matching** (`syncer.py`): replaced `startswith()` with `Path.is_relative_to()`.
- **Async desktop notify** (`api.py`): wrapped blocking `http.client` call in `asyncio.to_thread()`.
- **LiveRun polling fix** (`LiveRun.jsx`): replaced `setInterval` with `useRef`-based `setTimeout`.
- **ESLint restored in CI** (`ci.yml`): lint job now runs `npm run lint`.
- **CI syntax check** (`ci.yml`): replaced hardcoded file list with `python -m compileall backend/ -q`.

### Minor Fixes
- **Timezone consistency** (`watcher.py`): `datetime.now()` → `datetime.now(timezone.utc)`.
- **UTC string handling** (`LiveRun.jsx`): normalizes Python's `+00:00` suffix to `Z` before parsing.
- **Memory leak fix** (`LogsViewer.jsx`): `URL.revokeObjectURL()` called after CSV export.
- **Dynamic version chip** (`GhostBackup.jsx`): fetches version from IPC instead of hardcoded `v2.0.0`.
- **Duplicate exclusion check** (`BackupConfig.jsx`): prevents adding duplicate patterns.
- **Platform-aware restore path** (`RestoreUI.jsx`): defaults to Linux path on non-Windows.
- **Keyboard accessibility** (`GhostBackup.jsx`): nav items have `role="button"`, `tabIndex`, `onKeyDown`.
- **Coverage threshold** (`ci.yml`): raised from 60% to 70%.
- **Node 22 LTS** (`ci.yml`): added to frontend test matrix.

### New Tests (21 tests across 4 new files)

| File | Tests |
|------|-------|
| `test_syncer_copy.py` | 6 — `copy_file()`: basic, atomic write, checksum, dirs, encryption, secondary SSD |
| `test_syncer_restore.py` | 5 — `restore_files()`: basic, decryption, path traversal blocked, dirs, missing file |
| `test_syncer_verify.py` | 3 — `verify_backups()`: intact, corrupted, missing |
| `test_watcher.py` | 5 — `_SourceHandler`: debounce, cooldown, UTC timezone, ghosttmp ignored, exclusions |
| `test_manifest.py` | +1 — `flush()` batch commit verification |

---

## v2.1.0 — Security Fixes, Streaming Encryption & Production Hardening

### Critical Fixes
- **Streaming AES-256-GCM encryption** (`syncer.py`): replaced Fernet's whole-file-in-memory encryption with chunked AES-256-GCM streaming — memory usage is now constant regardless of file size. Legacy Fernet-encrypted backups are auto-detected and decrypted transparently.
- **Thread-safe `_active_run` mutations** (`api.py`): added `threading.Lock` around all compound operations on the shared run state dict.

### Important Fixes
- **`datetime.utcnow()` replaced** (`manifest.py`, `api.py`, `syncer.py`): all deprecated calls replaced with `datetime.now(timezone.utc)` for Python 3.12+ compatibility.
- **CI lint job fixed** (`ci.yml`): removed duplicate flake8 step, restored ESLint.
- **Secondary SSD infinite-recursion guard** (`syncer.py`): added `_skip_secondary` parameter to `copy_file()`.
- **Notification server authenticated** (`main.js`, `api.py`): port 8766 now validates `X-API-Key` header.
- **`ThreadPoolExecutor` shutdown** (`api.py`): changed to `shutdown(wait=True, cancel_futures=True)`.
- **CORS `"null"` origin removed** (`api.py`).

### Minor Fixes
- **`schema_version` table populated** (`manifest.py`).
- **Retention UI max corrected** (`Settings.jsx`): `weekly_days` input max raised to 3650.
- **Electron-builder config paths fixed** (`package.json`).
- **Duplicate LIKE escaping consolidated** (`manifest.py`).
- **"Start with Windows" hidden on non-Windows** (`main.js`).
- **Adaptive LiveRun polling** (`LiveRun.jsx`): 1s during active runs, 5s when idle.

---

## v2.0.0 — Architecture Overhaul, Security Hardening & Full Test Suite

### Security
- **CSP hardened**: removed `unsafe-inline` from `script-src`.
- **`asyncio.Lock` on backup guard**: `_active_run` check-and-set is now atomic.
- **Encryption key rotation UI**: new `POST /settings/encryption/generate-key` endpoint.

### Frontend — Component Architecture
- **`src/GhostBackup.jsx`** rewritten from 2134 lines to ~110 lines.
- All UI extracted into `src/pages/` and `src/components/`.
- **`src/styles.css`** and **`src/splash.css`**: all 600+ lines of CSS extracted from JSX.

### Backend — Bug Fixes
- **`version_count` removed from API surface**: was accepted but had no effect on the pruner.
- **`setup_helper.py`**: YAML config patching replaced with proper `yaml.safe_load` → mutate → `yaml.dump`.
- **`utils.py`** (new): shared `fmt_bytes` / `fmt_duration` helpers extracted.

### Tests — Full Coverage Added

**Backend (214 pytest tests across 10 files):**

| File | Tests |
|------|-------|
| `test_utils.py` | 20 |
| `test_reporter.py` | 25 |
| `test_crypto.py` | 12 |
| `test_syncer_scan.py` | 18 |
| `test_setup_helper.py` | 8 |

**Frontend (60 vitest tests across 3 files):**

| File | Tests |
|------|-------|
| `components.test.jsx` | 29 |
| `api-client.test.js` | +16 |

---

## v1.3.0 — Frontend API Client Fixes

- Added `export default api` to `api-client.js`.
- Added 20 named convenience methods covering all endpoints.
- Replaced 6 raw `fetch()` calls in `GhostBackup.jsx` with authenticated `api.*()` wrapper.
- Added 16 new frontend tests.

---

## v1.2.0 — Automated Installer & Test Coverage

- **`install.bat`** (new): one-step Windows installer.
- **`setup_helper.py`** (new): interactive setup wizard.
- **`test_api.py`** (new): 30 FastAPI endpoint tests.
- **`api-client.test.js`** (new): 22 Vitest unit tests.

---

## v1.1.0 — Code Quality & Bug Fixes

- Refactored `api.py`, `manifest.py`, `syncer.py`, `watcher.py`, `config.py`, `reporter.py`, `scheduler.py`.
- Fixed thread-safety bugs in `manifest.py` and `reporter.py`.
- Removed blocking `Atomics.wait()` from `main.js`.
- Added pytest suite: `test_manifest.py`, `test_config.py`, `test_syncer_utils.py`, `test_scheduler_utils.py`.
