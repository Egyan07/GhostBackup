# GhostBackup v3.0.0 — Rating Push Design Spec

**Date:** 2026-03-31
**Goal:** Push codebase rating from 8.5 to 9.0+ by addressing the 7 gaps identified in the code review.
**Context:** Single-machine backup tool for Red Parrot Accounting (UK). One IT person. Sensitive accounting data. Windows-only deployment.

---

## Phase 1: End-to-End Integration Test

**File:** `backend/tests/test_e2e_pipeline.py`

A single test class that exercises the full backup pipeline with real files, real encryption, and real database — no mocks for the core path.

### Test Flow
1. Create a temporary source directory with 5-10 files of varying sizes (1KB to 1MB), including nested subdirectories
2. Create a temporary SSD destination directory
3. Generate a real Fernet encryption key
4. Instantiate real `ConfigManager` (from config.yaml.example, patched with temp paths), real `ManifestDB` (in-memory or temp file), real `LocalSyncer`
5. Run `scan_source()` → assert all files detected as changed
6. Run `copy_file()` for each file → assert destination files exist and are encrypted (start with `GBENC1` magic header)
7. Run `verify_backups()` → assert all verified, 0 corrupt, 0 missing
8. Run `restore_files()` to a new temp directory → assert restored files match originals byte-for-byte (compare xxhash)
9. Verify manifest DB has correct run record, file records, and hash cache entries

### Test Variants
- `test_e2e_full_backup_cycle` — happy path above
- `test_e2e_incremental_skips_unchanged` — run backup twice, second run should skip all files
- `test_e2e_key_fingerprint_tracked` — verify key_fingerprint column populated in file records

### Dependencies
- Uses `tmp_path` fixture (pytest built-in)
- Generates real Fernet key via `cryptography.fernet.Fernet.generate_key()`
- Uses real `ManifestDB` with temp SQLite file
- Uses real `_CryptoHelper` with real encryption/decryption

---

## Phase 2: Encryption Key Protection (keyring)

**Files:** `backend/config.py`, `electron/main.js`, `backend/requirements.txt`, `src/pages/Settings.jsx`

### Architecture
- Add `keyring` to `requirements.txt`
- `config.py` gains a `KeyringManager` class that wraps `keyring.get_password()` / `keyring.set_password()`
- Service name: `"GhostBackup"`, usernames: `"encryption_key"`, `"smtp_password"`, `"hkdf_salt"`

### Startup Flow
1. Try `keyring.get_password("GhostBackup", "encryption_key")`
2. If found → use it
3. If not found → check `GHOSTBACKUP_ENCRYPTION_KEY` env var
4. If env var found → migrate to keyring, clear from `.env.local` (rewrite file without that line)
5. If neither → encryption disabled (fail-hard if encryption_config_enabled)

### Migration Logic (`_migrate_env_to_keyring()`)
```python
for key_name, env_var in KEYRING_SECRETS:
    env_val = os.getenv(env_var)
    if env_val and not keyring.get_password("GhostBackup", key_name):
        keyring.set_password("GhostBackup", key_name, env_val)
        _remove_from_env_file(env_var)
        logger.info(f"Migrated {env_var} to Windows Credential Manager")
```

### Fallback
- If `keyring` import fails (headless, CI, Linux), fall back to env var silently
- Log warning: "keyring unavailable — using environment variables"

### Electron IPC Changes
- `credentials:save` handler: write to keyring instead of `.env.local` when keyring available
- `credentials:status` handler: report keyring vs env var storage method

### Settings UI
- New status line: "Key Storage: Windows Credential Manager" or "Key Storage: Environment File (.env.local)"
- No new buttons needed — migration is automatic

### Secrets Migrated
| Secret | Env Var | Keyring Username |
|--------|---------|-----------------|
| Encryption key | `GHOSTBACKUP_ENCRYPTION_KEY` | `encryption_key` |
| SMTP password | `GHOSTBACKUP_SMTP_PASSWORD` | `smtp_password` |
| HKDF salt | `GHOSTBACKUP_HKDF_SALT` | `hkdf_salt` |

---

## Phase 3: Startup Self-Check

**Files:** `backend/api.py`, `backend/syncer.py`

### Implementation
- New function `_startup_spot_check(syncer, manifest)` in `api.py`
- Called from `lifespan` after all services initialized, as a background task (does not block `/health`)
- Queries manifest for the last successful run's files, picks 5 at random
- Calls `syncer.verify_files(file_list)` (new method — subset of `verify_backups`)
- If any fail: push critical alert via reporter

### syncer.py Addition
```python
def verify_files(self, file_records: list[dict]) -> dict:
    """Verify a specific list of files. Returns {verified, failed, missing, details}."""
    # Same logic as verify_backups but for a specific file list
```

### Behaviour
- If no previous backups exist: skip silently, log info
- If SSD not connected at startup: skip, log warning (SSD polling will catch it later)
- Runs once at startup only — not periodic (the scheduled verify handles ongoing checks)
- Target: complete in under 3 seconds for 5 files

---

## Phase 4: Backup Immutability Window

**Files:** `backend/config.py`, `backend/syncer.py`, `backend/api.py`, `backend/config/config.yaml.example`

### Config
```yaml
retention:
  immutable_days: 7    # Backups younger than this CANNOT be deleted
```

### Validation
- Minimum: 7 days (cannot be set lower)
- Default: 7 days
- Added to `_validate_update()` in config.py

### Enforcement Points

1. **`syncer.prune_old_backups()`** — already respects `guard_days`. Add explicit immutability check: if file's `started_at` is within `immutable_days`, skip it regardless of retention policy. Log as "immutable, skipping".

2. **`POST /settings/prune`** — the manual prune endpoint. Before running, check that no immutable backups would be affected. If the prune would only touch non-immutable backups, proceed. The immutability is enforced at the syncer level anyway, but the API should surface it.

3. **No direct file deletion endpoint exists** — so no additional enforcement needed there.

### API Response
When prune skips immutable files:
```json
{
  "message": "Prune complete",
  "removed": 12,
  "immutable_skipped": 3,
  "immutable_until": "2026-04-07T08:00:00Z"
}
```

### Config Property
```python
@property
def immutable_days(self) -> int:
    return self._data.get("retention", {}).get("immutable_days", 7)
```

---

## Phase 5: Restore Drill Reminder (with tracking)

**Files:** `backend/manifest.py`, `backend/scheduler.py`, `backend/reporter.py`, `backend/api.py`, `src/pages/Settings.jsx`

### Database Schema (manifest.py migration v4)
```sql
CREATE TABLE IF NOT EXISTS restore_drills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    due_date     TEXT NOT NULL,
    completed_at TEXT,
    restore_run_id INTEGER,
    notes        TEXT
);
CREATE INDEX idx_drills_due ON restore_drills(due_date DESC);
```

### Scheduler Job
- New job: `_restore_drill_check()`, runs daily at noon (after the backup window)
- Logic:
  1. Query `manifest.get_last_drill_completion()` → returns date or None
  2. Calculate days since last drill (or since first backup if no drills yet)
  3. Escalation:
     - Day 30: info alert — "Monthly restore drill due. Go to Restore and verify a recent backup."
     - Day 37: warn alert + email — "Restore drill overdue by 1 week."
     - Day 44: critical alert + email — "Restore drill overdue by 2 weeks. Compliance risk."
  4. Track alert state to avoid duplicate alerts (similar to `_missed_alerted` pattern)

### Auto-Recording Drills
- In `POST /restore` endpoint: after a successful non-dry-run restore, call `manifest.record_drill(restore_run_id)`
- This inserts a new row in `restore_drills` with `completed_at = now()` and the run_id

### Manifest Methods
```python
def record_drill(self, restore_run_id: int = None, notes: str = "") -> int:
    """Record a completed restore drill."""

def get_last_drill_completion(self) -> Optional[str]:
    """ISO timestamp of the most recent completed drill, or None."""

def get_drill_history(self, limit: int = 12) -> list[dict]:
    """Last N drill records for audit display."""
```

### Settings UI Addition
Below the "Verify Integrity" card, add a "Restore Drill" card:
```
Restore Drill
Last completed: 2026-03-15 (16 days ago)
Next due: 2026-04-15
Status: On track

[View Drill History]
```
- Green if completed within 30 days
- Yellow if 30-37 days
- Red if 37+ days
- "View Drill History" opens a small table of past drills

### API Endpoints
- `GET /settings/drill-status` — returns last_completed, next_due, days_overdue, history
- No manual "mark as complete" endpoint — drills are auto-recorded from actual restores

---

## Phase 6: Structured Error Codes

**Files:** `backend/api.py`, `backend/errors.py` (new), `SETUP.md`

### Error Code Registry (`backend/errors.py`)
```python
class GBError:
    """Structured error with code, message, and fix suggestion."""
    def __init__(self, code: str, message: str, fix: str = ""):
        self.code = code
        self.message = message
        self.fix = fix

# Registry
ERRORS = {
    # Encryption
    "GB-E001": GBError("GB-E001", "Encryption key not set", "Set GHOSTBACKUP_ENCRYPTION_KEY in .env.local or Windows Credential Manager"),
    "GB-E002": GBError("GB-E002", "Encryption initialization failed", "Check that the key is a valid Fernet key (base64-encoded, 44 chars)"),
    "GB-E003": GBError("GB-E003", "Key fingerprint mismatch on restore", "The file was encrypted with a different key. Provide the original key."),

    # SSD
    "GB-E010": GBError("GB-E010", "Primary SSD not connected", "Connect the backup SSD and verify the path in Settings"),
    "GB-E011": GBError("GB-E011", "SSD free space critically low", "Prune old backups or connect a larger drive"),

    # Backup
    "GB-E020": GBError("GB-E020", "Backup already in progress", "Wait for the current run to finish or stop it"),
    "GB-E021": GBError("GB-E021", "Source folder not found", "Verify the source path exists and is accessible"),
    "GB-E022": GBError("GB-E022", "Circuit breaker triggered", "Too many failures in one library. Check file permissions."),
    "GB-E023": GBError("GB-E023", "Backup job timed out", "Increase max_job_minutes or reduce source size"),

    # Config
    "GB-E030": GBError("GB-E030", "Invalid configuration value", "Check the field constraints in SETUP.md"),
    "GB-E031": GBError("GB-E031", "Retention below compliance minimum", "weekly_days cannot be less than compliance_years * 365"),
    "GB-E032": GBError("GB-E032", "Cannot delete immutable backup", "Backups within the immutable window cannot be pruned"),

    # Restore
    "GB-E040": GBError("GB-E040", "Restore from failed run rejected", "Select a successful or partial run instead"),
    "GB-E041": GBError("GB-E041", "No files found for restore", "The selected run has no transferable files"),
    "GB-E042": GBError("GB-E042", "Path traversal blocked", "The restore path attempted to escape the destination directory"),

    # SMTP
    "GB-E050": GBError("GB-E050", "SMTP test failed", "Verify host, port, credentials, and TLS settings"),

    # System
    "GB-E060": GBError("GB-E060", "Verify rejected during backup", "Wait for the backup to finish before running verification"),
    "GB-E061": GBError("GB-E061", "Prune rejected during backup", "Wait for the backup to finish before pruning"),
}
```

### API Integration
Replace raw `HTTPException` calls with a helper:
```python
def raise_gb_error(code: str, status: int = 400, detail_override: str = None):
    err = ERRORS[code]
    raise HTTPException(
        status_code=status,
        detail={
            "code": err.code,
            "message": detail_override or err.message,
            "fix": err.fix,
        },
    )
```

### Backwards Compatibility
- The `detail` field is now a dict instead of a string
- FastAPI serializes this to JSON automatically
- Frontend already does `j.detail || j.message` — add `j.detail?.message || j.detail` fallback

### SETUP.md Addition
Add a "Error Code Reference" section with a table:
```
| Code    | Meaning                        | Fix |
|---------|-------------------------------|-----|
| GB-E001 | Encryption key not set         | Set GHOSTBACKUP_ENCRYPTION_KEY... |
```

---

## Phase 7: Deep Health Endpoint

**Files:** `backend/api.py`

### Endpoint
```
GET /health/deep
```
- Authenticated (requires X-API-Key)
- Rate limited: 10/minute
- Not cached — runs checks fresh each call

### Response
```json
{
  "ssd_connected": true,
  "ssd_free_gb": 234.5,
  "secondary_ssd_connected": true,
  "last_backup_age_hours": 2.3,
  "last_backup_status": "success",
  "encryption_active": true,
  "key_storage": "keyring",
  "manifest_ok": true,
  "manifest_size_mb": 12.4,
  "spot_check": {
    "checked": 5,
    "passed": 5,
    "failed": 0
  },
  "scheduler_running": true,
  "next_backup": "2026-04-01T08:00:00Z",
  "restore_drill_overdue": false,
  "restore_drill_days_remaining": 14,
  "version": "3.0.0",
  "overall": "healthy"
}
```

### `overall` Logic
- `"healthy"` — all checks pass
- `"degraded"` — non-critical issue (secondary SSD disconnected, drill overdue, spot check had warnings)
- `"unhealthy"` — critical issue (primary SSD disconnected, encryption inactive, last backup failed, spot check failed)

### Implementation
```python
@app.get("/health/deep")
@_limiter.limit("10/minute")
async def health_deep(request: Request, ...):
    ssd = get_ssd_status(cfg.ssd_path)
    last_run = manifest.get_latest_run()
    spot = await loop.run_in_executor(None, lambda: syncer.verify_files(random_sample(5)))
    drill = manifest.get_last_drill_completion()
    # ... assemble response
```

### Uptime Monitor Integration
The IT person adds a check in their monitoring tool:
- URL: `http://localhost:8765/health/deep`
- Header: `X-API-Key: <token>`
- Alert if: `overall != "healthy"` or HTTP status != 200

---

## Version & Documentation Updates

- Bump to v3.0.0 (significant feature addition)
- CHANGELOG.md: new v3.0.0 section
- README.md: update features table, security table, API endpoints
- SETUP.md: error code reference table, keyring setup notes, restore drill documentation

---

## Implementation Order

| Phase | Feature | Depends On |
|-------|---------|-----------|
| 1 | E2E integration test | None |
| 2 | Keyring encryption | None |
| 3 | Startup self-check | Phase 1 (verify_files method) |
| 4 | Immutability window | None |
| 5 | Restore drill reminder | None |
| 6 | Structured error codes | None |
| 7 | Deep health endpoint | Phases 3, 5 (spot_check, drill status) |

Phases 1, 2, 4, 5, 6 are independent and can be parallelized.
Phase 3 depends on the `verify_files()` method introduced in Phase 1.
Phase 7 depends on Phases 3 and 5 for spot-check and drill data.
