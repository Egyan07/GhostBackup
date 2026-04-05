# GhostBackup

> **Windows Only** — macOS and Linux are not supported.

### Local. Encrypted. Audited. Yours.

![CI](https://img.shields.io/github/actions/workflow/status/Egyan07/GhostBackup/ci.yml?label=CI)
![Tests](https://img.shields.io/badge/tests-675%2B%20passing-brightgreen)
![Backend Coverage](https://img.shields.io/badge/backend%20coverage-90%25-brightgreen)
![Frontend Coverage](https://img.shields.io/badge/frontend%20coverage-75%25-green)
![License](https://img.shields.io/github/license/Egyan07/GhostBackup)
![Node](https://img.shields.io/badge/node-%3E%3D22-339933?logo=node.js&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)

**Author: [Egyan07](https://github.com/Egyan07)** | **Deployed at [Red Parrot Accounting](https://github.com/Egyan07/GhostBackup) (UK)**

GhostBackup runs on a dedicated Windows machine, backs up your source folders to one or two local SSDs on a daily schedule, encrypts every file with AES-256-GCM, verifies integrity with xxhash, and emails you if anything fails. **No cloud. No subscriptions. No IT staff required.**

---

## How It Works

```
Source Folders ──> Scan & Encrypt ──> Copy to SSD(s) ──> Verify & Log
     |                  |                   |                  |
  Your files     AES-256-GCM +       Primary + optional    xxhash check
  on disk       per-file nonce      secondary SSD backup   + SQLite audit
```

**1. Schedule** — APScheduler triggers daily at your configured time, or Watchdog detects file changes in real-time.
**2. Encrypt** — Every file is encrypted with AES-256-GCM (streaming, constant memory, per-file nonce).
**3. Copy** — Files are written to the primary SSD and optionally mirrored to a secondary SSD.
**4. Verify** — xxhash checksums confirm integrity. Results logged to SQLite. Failures trigger email alerts.

---

## Screenshots

| Dashboard | Live Run | Restore |
|-----------|----------|---------|
| ![Dashboard](screenshots/Dashboard.png) | ![Live Run](screenshots/Live%20Run.png) | ![Restore](screenshots/Restore.png) |
| *Run summary, SSD usage, next backup* | *Per-library progress and file feed* | *Date selection with dry-run preview* |

| Email Alert |
|-------------|
| ![Email Alert](screenshots/Email%20Alerts.png) |
| *SMTP alert confirming email notifications are configured* |

---

## Tech Stack

![Electron](https://img.shields.io/badge/Electron_41-191970?style=for-the-badge&logo=electron&logoColor=white)
![React](https://img.shields.io/badge/React_18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![Vite](https://img.shields.io/badge/Vite_7-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Vitest](https://img.shields.io/badge/Vitest-6E9F18?style=for-the-badge&logo=vitest&logoColor=white)

---

## Comparison

| Feature | GhostBackup | Backblaze B2 | Veeam Free | IDrive |
|---------|:-----------:|:------------:|:----------:|:------:|
| AES-256-GCM encryption | :white_check_mark: | :white_check_mark: | :x: | :white_check_mark: |
| No cloud / no vendor lock-in | :white_check_mark: | :x: | :white_check_mark: | :x: |
| No subscription cost | :white_check_mark: | :x: | :white_check_mark: | :x: |
| GUI dashboard + live progress | :white_check_mark: | :x: | :white_check_mark: | :white_check_mark: |
| Per-file integrity verification | :white_check_mark: | :x: | :x: | :x: |
| Dry-run restore preview | :white_check_mark: | :x: | :x: | :x: |
| Full audit trail + CSV export | :white_check_mark: | :x: | :white_check_mark: | :white_check_mark: |
| Open source | :white_check_mark: | :x: | :x: | :x: |

---

## Features

### Security & Encryption
- **AES-256-GCM** streaming encryption with per-file random nonce and constant memory usage
- **Fail-hard mode** — refuses to start if encryption is enabled but key is missing (no silent fallback)
- **Key fingerprint tracking** — detects key rotation mismatches on restore
- **Windows Credential Manager** for key storage (falls back to `.env.local` for CI)
- **Fine-grained CSP** — 10 Electron security directives including `frame-ancestors 'none'`, `object-src 'none'`
- **Rate-limited API** with timing-safe token authentication (`hmac.compare_digest`)
- **Path traversal protection** on all file restore operations

### Backup & Restore
- **Scheduled daily backups** with configurable timezone (APScheduler)
- **Real-time file watching** via Watchdog (15s debounce, 120s cooldown)
- **Dual-SSD redundancy** — primary + optional secondary drive (3 copies total with source)
- **Dry-run restore** — preview exactly which files will be restored before writing
- **Smart retention** — daily/weekly policies with 7-year compliance floor and immutable guard window
- **Automated pruning** that respects retention rules and the immutable window

### Monitoring & Auditability
- **Startup self-check** — 5 random files verified on every launch
- **Email alerts** (SMTP) on failure, partial success, and completion
- **Desktop notifications** for all backup outcomes
- **Restore drill tracking** with escalating reminders (30/37/44 days)
- **Full audit trail** — every config change, run, and file result logged to SQLite
- **CSV export** of run history from the Logs page

### Developer Experience
- **675+ automated tests** across backend, frontend, and Electron
- **Prettier + Husky** pre-commit hooks enforce formatting
- **OpenAPI schema** auto-generated and validated in CI
- **Structured error codes** (GB-Exxx) with actionable fix suggestions
- **TypeScript strict mode** across the entire frontend

---

## Quick Start

### Option A — Installer (Recommended)

1. Download `GhostBackup_Setup.exe` from **[Releases](https://github.com/Egyan07/GhostBackup/releases)**
2. Run the installer and follow prompts
3. Launch from desktop or start menu

### Option B — Manual Setup

**Requirements:** Windows 10/11, Python 3.10+, Node.js 22+, one SSD

```bash
git clone https://github.com/Egyan07/GhostBackup.git
cd GhostBackup
install.bat    # guided setup: dependencies, encryption key, config
start.bat      # launch the app
```

Full guide: **[SETUP.md](SETUP.md)** | Disaster recovery: **[RECOVERY.md](RECOVERY.md)** | Offsite backup: **[OFFSITE.md](OFFSITE.md)**

---

## Testing

```bash
npm test                    # all tests (frontend + electron)
cd backend && pytest tests/ -v --cov=.  # backend tests
```

| Suite | Tests | Coverage | CI |
|-------|-------|----------|----|
| Backend (pytest) | 407 | 90% line | :white_check_mark: |
| Frontend (Vitest) | 260+ | 75%+ stmt | :white_check_mark: |
| Electron (Vitest) | 77 | — | :white_check_mark: |

Covers: backup engine, all API endpoints, all 6 pages, all 8 components, IPC/preload/CSP, input validation, and auth edge cases.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ ELECTRON (main.js)                                          │
│ Spawns backend, generates API token, system tray, CSP       │
└──────────────────────────┬──────────────────────────────────┘
                           │ token via environment variable
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ FASTAPI BACKEND (localhost:8765)                             │
│                                                             │
│ Auth Middleware ─── APScheduler ─── Watchdog                │
│                                                             │
│ syncer.py: scan → encrypt → copy → verify → prune          │
│ manifest.py: SQLite (runs, files, audit trail)              │
│ reporter.py: email alerts + desktop notifications           │
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │ HTTP polling (localhost only)
┌──────────────────────────┴──────────────────────────────────┐
│ REACT + TYPESCRIPT FRONTEND (sandbox + CSP enforced)        │
│ Dashboard · Live Run · Logs · Restore · Settings · Alerts   │
└─────────────────────────────────────────────────────────────┘
```

---

## API

31 endpoints. All require `X-API-Key` except `/health`. Full OpenAPI schema at `/openapi.json`.

<details>
<summary>View all endpoints</summary>

| Group | Method | Endpoint | Description |
|-------|--------|----------|-------------|
| Core | GET | /health | Health check (no auth) |
| Core | GET | /dashboard | Dashboard summary |
| Core | GET | /health/deep | Comprehensive health check |
| Runs | POST | /run/start | Start a backup run |
| Runs | POST | /run/stop | Cancel active run |
| Runs | GET | /run/status | Active run state |
| Runs | GET | /runs | Run history |
| Runs | GET | /runs/:id | Single run detail |
| Runs | GET | /runs/:id/logs | Log entries for a run |
| Runs | POST | /verify | Re-hash all backups |
| Restore | POST | /restore | Restore files |
| Config | GET | /config | Current configuration |
| Config | PATCH | /config | Update configuration |
| Config | GET | /config/audit | Config change audit trail |
| Config | POST | /config/sites | Add a source folder |
| Config | PATCH | /config/sites/:name | Update source |
| Config | DELETE | /config/sites/:name | Remove source |
| Settings | PATCH | /settings/smtp | Update SMTP |
| Settings | POST | /settings/smtp/test | Send test email |
| Settings | PATCH | /settings/retention | Update retention |
| Settings | POST | /settings/prune | Trigger prune |
| Settings | POST | /settings/encryption/generate-key | New encryption key |
| Settings | GET | /settings/drill-status | Drill status |
| Monitor | GET | /ssd/status | Disk usage |
| Monitor | GET | /alerts | Alert list |
| Monitor | POST | /alerts/:id/dismiss | Dismiss alert |
| Monitor | POST | /alerts/dismiss-all | Dismiss all |
| Monitor | GET | /watcher/status | Watcher state |
| Monitor | POST | /watcher/start | Start watcher |
| Monitor | POST | /watcher/stop | Stop watcher |

</details>

---

## Configuration

**File:** `backend/config/config.yaml` (generated by `install.bat`)
**Template:** `backend/config/config.yaml.example`

Key settings: SSD paths, encryption toggle, source folders, retention policy (daily/weekly/compliance), schedule time and timezone, circuit breaker threshold (5%), watcher debounce/cooldown.

**Environment Variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `GHOSTBACKUP_ENCRYPTION_KEY` | If encryption on | AES-256 key in Credential Manager. **If lost, backups are unrecoverable.** |
| `GHOSTBACKUP_HKDF_SALT` | Recommended | Per-installation salt for key derivation |
| `GHOSTBACKUP_SMTP_PASSWORD` | If email on | SMTP password (Gmail: use App Password) |
| `GHOSTBACKUP_API_PORT` | No (default: 8765) | Backend port |
| `GHOSTBACKUP_API_TOKEN` | Auto | Generated per launch. Do not set manually |

---

## Security

| Layer | Implementation |
|-------|----------------|
| Encryption | AES-256-GCM, streaming, per-file nonce, HKDF salt, versioned header. Fail-hard if key missing. |
| Authentication | Per-launch token via `crypto.randomBytes(32)`, timing-safe comparison, rate limiting |
| Path Safety | Traversal validation on all restore paths (null bytes, `..`, drive letters) |
| Electron | Sandbox + context isolation + 10-directive CSP (no unsafe-eval, pinned connect-src) |
| Database | `PRAGMA synchronous=FULL`, WAL checkpoints, 3-copy manifest rotation to SSD |
| Integrity | xxhash at source, verified after every copy. Key fingerprint stored per file |
| Process Safety | Port conflict detection validates process identity before termination |

**Not covered:** No external security audit. API is localhost-only without TLS. Key stored in Credential Manager (`.env.local` fallback for CI).

---

## Retention & Compliance

> GhostBackup provides tools that *support* compliance. It is not a compliance certification. Consult a legal professional for your jurisdiction.

| Policy | Default | Purpose |
|--------|---------|---------|
| Daily | 365 days | Daily snapshots for 1 year |
| Weekly | 2,555 days | Weekly snapshots for 7 years |
| Compliance floor | 7 years | Cannot reduce below this |
| Guard days | 7 days | Prevents accidental pruning of recent backups |

Full audit trail: config changes, run history, per-file records, integrity verification results — all in SQLite with CSV export.

---

## Limitations

| Limitation | Detail |
|------------|--------|
| Windows only | Windows 10/11 required |
| Local drives only | No cloud, NAS, or network shares |
| No offsite | Local redundancy only — see [OFFSITE.md](OFFSITE.md) |
| No deduplication | Full file copy on each run |
| Single machine | No multi-user or networked deployment |
| Scale | Tested to ~50GB. 500GB+ untested |
| Key loss | If encryption key is lost from all locations, backups are permanently unrecoverable |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Port already in use" | Quit via tray icon (X just hides to tray) |
| "Service stopped unexpectedly" | `pip install -r backend/requirements.txt` then relaunch |
| Email not arriving | Gmail needs an App Password. Host: `smtp.gmail.com`, port: `587` |
| Backup not on schedule | Check sidebar dot is green. Verify `schedule.time` in config |
| Can't find file on SSD | Encrypted files use `.ghostenc`. Restore via the app |
| How to update | `git pull && pip install -r backend/requirements.txt && npm install --legacy-peer-deps` |

For disaster recovery (lost key, corrupted DB, SSD failure): **[RECOVERY.md](RECOVERY.md)**

---

## Contributing

Built for Red Parrot Accounting, open-sourced under MIT.

### Development Setup

```bash
git clone https://github.com/Egyan07/GhostBackup.git
cd GhostBackup
pip install -r backend/requirements.txt
npm install --legacy-peer-deps
npm run dev                 # starts React dev server + Electron
```

### Before Submitting a PR

```bash
cd backend && python -m pytest tests/ -v   # backend tests pass
npm test                                    # frontend + electron tests pass
npm run format:check                        # Prettier formatting
npm run lint                                # ESLint clean
```

**Contributions welcome:** Linux/macOS support, NAS/network drives, E2E test coverage, documentation.

---

## Use Cases

- **Accounting firms** — 7-year retention for UK Companies Act / HMRC
- **Legal offices** — encrypted client files with full audit trail
- **Financial services** — scheduled, verifiable backups with failure alerts
- **Medical practices** — encrypted patient records (verify GDPR/NHS DSPT separately)
- **Any small business** — encrypted, automated, auditable local backups without cloud dependency

---

## License

MIT License — see [LICENSE](LICENSE) for full text.

**Changelog:** [CHANGELOG.md](CHANGELOG.md)

---

*GhostBackup — Silent. Secure. Auditable.*
