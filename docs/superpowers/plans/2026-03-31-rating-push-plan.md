# GhostBackup v3.0.0 — Rating Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push codebase rating from 8.5 to 9.0+ by implementing 7 features: E2E test, keyring encryption, startup self-check, immutability window, restore drill tracking, structured error codes, and deep health endpoint.

**Architecture:** Each feature is an independent task (except Task 3 depends on Task 1's `verify_files` method, and Task 7 depends on Tasks 3+5). Features follow existing patterns: FastAPI endpoints with DI, ManifestDB for persistence, Reporter for alerts, Scheduler for periodic jobs.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, keyring, pytest, React/JSX

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `backend/tests/test_e2e_pipeline.py` | Create | E2E integration test |
| `backend/errors.py` | Create | Structured error code registry |
| `backend/config.py` | Modify | Add keyring support, immutable_days property |
| `backend/syncer.py` | Modify | Add verify_files(), immutability enforcement in prune |
| `backend/manifest.py` | Modify | Add restore_drills table (v4 migration), drill methods |
| `backend/api.py` | Modify | Startup spot-check, deep health, drill endpoint, error codes, prune immutability |
| `backend/scheduler.py` | Modify | Add restore drill check job |
| `backend/reporter.py` | Modify | Add drill reminder alerts |
| `backend/requirements.txt` | Modify | Add keyring dependency |
| `backend/config/config.yaml.example` | Modify | Add immutable_days default |
| `src/pages/Settings.jsx` | Modify | Add key storage indicator, drill status card |
| `src/api-client.js` | Modify | Add drill-status endpoint |
| `SETUP.md` | Modify | Add error code reference table |
| `CHANGELOG.md` | Modify | Add v3.0.0 section |
| `README.md` | Modify | Update features table, security table, API endpoints |
| `package.json` | Modify | Bump to 3.0.0 |

---

## Task 1: End-to-End Integration Test

**Files:**
- Create: `backend/tests/test_e2e_pipeline.py`

- [ ] **Step 1: Create test file with imports and helpers**

```python
"""
tests/test_e2e_pipeline.py — End-to-end integration tests for the full backup pipeline.

Exercises: scan → copy → verify → restore with real files, real encryption, real SQLite.
No mocks for the core pipeline.
"""

import os
import pytest
from pathlib import Path
from cryptography.fernet import Fernet

from config import ConfigManager
from manifest import ManifestDB
from syncer import LocalSyncer, _hash_file


def _make_real_config(tmp_path, ssd_path, source_path, encryption_key):
    """Create a real ConfigManager with a temp config.yaml pointing at temp dirs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(f"""
ssd_path: "{ssd_path}"
secondary_ssd_path: ""
encryption:
  enabled: true
schedule:
  time: "08:00"
  timezone: "Europe/London"
  max_job_minutes: 240
  retry_count: 3
  retry_delay_minutes: 30
performance:
  concurrency: 4
  max_file_size_gb: 5
  chunk_size_mb: 4
backup:
  verify_checksums: true
  version_count: 5
  exclude_patterns:
    - "~$*"
    - "*.tmp"
retention:
  daily_days: 365
  weekly_days: 2555
  compliance_years: 7
  guard_days: 7
  immutable_days: 7
circuit_breaker_threshold: 0.05
smtp:
  host: ""
  port: 587
  use_tls: true
  user: ""
  recipients: []
logging:
  level: INFO
  retention_days: 365
  log_dir: logs
watcher:
  debounce_seconds: 15
  cooldown_seconds: 120
sources:
  - label: TestSource
    path: "{source_path}"
    enabled: true
""")
    return config_file


def _populate_source(source_dir):
    """Create test files of varying sizes in the source directory."""
    files = {}
    # Small text file
    (source_dir / "readme.txt").write_text("Hello GhostBackup")
    files["readme.txt"] = b"Hello GhostBackup"
    # Binary file
    data_1kb = os.urandom(1024)
    (source_dir / "data.bin").write_bytes(data_1kb)
    files["data.bin"] = data_1kb
    # Nested directory
    sub = source_dir / "reports" / "2026"
    sub.mkdir(parents=True)
    report = b"Q1 financials " * 100
    (sub / "q1.xlsx").write_bytes(report)
    files[str(Path("reports/2026/q1.xlsx"))] = report
    # Another nested file
    (sub / "q2.xlsx").write_bytes(os.urandom(2048))
    files[str(Path("reports/2026/q2.xlsx"))] = (sub / "q2.xlsx").read_bytes()
    # File that should be excluded
    (source_dir / "~$temp.xlsx").write_bytes(b"temp lock file")
    return files
```

- [ ] **Step 2: Write the full backup cycle test**

```python
class TestE2EPipeline:

    def test_e2e_full_backup_cycle(self, tmp_path):
        """Full pipeline: scan → copy → record → verify → restore → compare."""
        # Setup
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        ssd_dir = tmp_path / "ssd"
        ssd_dir.mkdir()
        restore_dir = tmp_path / "restored"
        db_path = tmp_path / "test.db"

        files = _populate_source(source_dir)
        key = Fernet.generate_key()
        os.environ["GHOSTBACKUP_ENCRYPTION_KEY"] = key.decode()
        os.environ["GHOSTBACKUP_HKDF_SALT"] = "test-salt-e2e"

        try:
            config_file = _make_real_config(
                tmp_path, str(ssd_dir), str(source_dir), key.decode()
            )
            cfg = ConfigManager(config_path=config_file)
            manifest = ManifestDB(db_path=db_path)
            syncer = LocalSyncer(config=cfg, manifest=manifest)

            # 1. Scan
            source = {"label": "TestSource", "path": str(source_dir)}
            changed, skipped = syncer.scan_source(source, force_full=True)
            assert len(changed) == 4  # 4 files (excluding ~$temp.xlsx)
            assert skipped >= 1       # at least the excluded file

            # 2. Copy
            run_id = manifest.create_run(full_backup=True)
            for file_meta in changed:
                backup_path = syncer.copy_file(file_meta, run_id)
                manifest.record_file(run_id, file_meta, backup_path,
                                     key_fingerprint=syncer.key_fingerprint)
                # Verify backup file exists and is encrypted
                bp = Path(backup_path)
                assert bp.exists()
                header = bp.read_bytes()[:6]
                assert header == b"GBENC1", f"File should be encrypted: {bp.name}"

            # Finalize
            manifest.finalize_run(run_id, {
                "started_at": "2026-03-31T10:00:00",
                "finished_at": "2026-03-31T10:01:00",
                "status": "success",
                "files_transferred": len(changed),
                "files_skipped": skipped,
                "files_failed": 0,
                "bytes_transferred": sum(f["size"] for f in changed),
            })

            # 3. Verify
            result = syncer.verify_backups("TestSource")
            assert result["verified"] == 4
            assert result["failed"] == 0
            assert result["missing"] == 0

            # 4. Restore
            run_files = manifest.get_files(run_id)
            restore_result = syncer.restore_files(run_files, str(restore_dir))
            assert restore_result["restored"] == 4
            assert restore_result["failed"] == 0

            # 5. Compare byte-for-byte
            for rel_path, original_bytes in files.items():
                if rel_path.startswith("~$"):
                    continue  # excluded
                restored_file = restore_dir / rel_path
                assert restored_file.exists(), f"Missing restored file: {rel_path}"
                assert restored_file.read_bytes() == original_bytes, \
                    f"Content mismatch: {rel_path}"

            # 6. Verify manifest records
            run = manifest.get_run(run_id)
            assert run["status"] == "success"
            assert run["files_transferred"] == 4

            # 7. Verify hash cache populated
            for file_meta in changed:
                cached = manifest.get_file_hash(file_meta["original_path"])
                assert cached is not None
                assert cached["xxhash"] == file_meta["xxhash"]

        finally:
            os.environ.pop("GHOSTBACKUP_ENCRYPTION_KEY", None)
            os.environ.pop("GHOSTBACKUP_HKDF_SALT", None)

    def test_e2e_incremental_skips_unchanged(self, tmp_path):
        """Second backup run should skip all files (nothing changed)."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        ssd_dir = tmp_path / "ssd"
        ssd_dir.mkdir()
        db_path = tmp_path / "test.db"

        (source_dir / "file.txt").write_text("stable content")
        key = Fernet.generate_key()
        os.environ["GHOSTBACKUP_ENCRYPTION_KEY"] = key.decode()
        os.environ["GHOSTBACKUP_HKDF_SALT"] = "test-salt-e2e"

        try:
            config_file = _make_real_config(
                tmp_path, str(ssd_dir), str(source_dir), key.decode()
            )
            cfg = ConfigManager(config_path=config_file)
            manifest = ManifestDB(db_path=db_path)
            syncer = LocalSyncer(config=cfg, manifest=manifest)
            source = {"label": "TestSource", "path": str(source_dir)}

            # First run — should detect 1 changed file
            changed1, _ = syncer.scan_source(source, force_full=True)
            assert len(changed1) == 1
            run_id = manifest.create_run(full_backup=True)
            for fm in changed1:
                bp = syncer.copy_file(fm, run_id)
                manifest.record_file(run_id, fm, bp)
            manifest.finalize_run(run_id, {
                "started_at": "2026-03-31T10:00:00",
                "status": "success",
                "files_transferred": 1, "files_skipped": 0, "files_failed": 0,
                "bytes_transferred": changed1[0]["size"],
            })

            # Second run — incremental should skip everything
            changed2, skipped2 = syncer.scan_source(source, force_full=False)
            assert len(changed2) == 0
            assert skipped2 == 1

        finally:
            os.environ.pop("GHOSTBACKUP_ENCRYPTION_KEY", None)
            os.environ.pop("GHOSTBACKUP_HKDF_SALT", None)

    def test_e2e_key_fingerprint_tracked(self, tmp_path):
        """Key fingerprint must be stored in the file record."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        ssd_dir = tmp_path / "ssd"
        ssd_dir.mkdir()
        db_path = tmp_path / "test.db"

        (source_dir / "doc.txt").write_text("fingerprint test")
        key = Fernet.generate_key()
        os.environ["GHOSTBACKUP_ENCRYPTION_KEY"] = key.decode()
        os.environ["GHOSTBACKUP_HKDF_SALT"] = "test-salt-e2e"

        try:
            config_file = _make_real_config(
                tmp_path, str(ssd_dir), str(source_dir), key.decode()
            )
            cfg = ConfigManager(config_path=config_file)
            manifest = ManifestDB(db_path=db_path)
            syncer = LocalSyncer(config=cfg, manifest=manifest)

            source = {"label": "TestSource", "path": str(source_dir)}
            changed, _ = syncer.scan_source(source, force_full=True)
            run_id = manifest.create_run()
            for fm in changed:
                bp = syncer.copy_file(fm, run_id)
                manifest.record_file(run_id, fm, bp,
                                     key_fingerprint=syncer.key_fingerprint)

            # Check the stored fingerprint
            files = manifest.get_files(run_id)
            assert len(files) == 1
            assert files[0]["key_fingerprint"] is not None
            assert len(files[0]["key_fingerprint"]) == 16  # 16 hex chars
            assert files[0]["key_fingerprint"] == syncer.key_fingerprint

        finally:
            os.environ.pop("GHOSTBACKUP_ENCRYPTION_KEY", None)
            os.environ.pop("GHOSTBACKUP_HKDF_SALT", None)
```

- [ ] **Step 3: Run the tests**

Run: `cd /home/Egyan/GhostBackup && .venv/bin/python -m pytest backend/tests/test_e2e_pipeline.py -v`
Expected: 3 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_e2e_pipeline.py
git commit -m "test: add E2E integration tests for full backup pipeline"
```

---

## Task 2: Encryption Key Protection (keyring)

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py:131-156`
- Modify: `electron/main.js:503-531`
- Modify: `src/pages/Settings.jsx`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Add keyring to requirements.txt**

Add to the end of `backend/requirements.txt`:

```
keyring>=25.0.0
```

Install: `.venv/bin/pip install keyring>=25.0.0`

- [ ] **Step 2: Write failing tests for keyring integration**

Add to `backend/tests/test_config.py`:

```python
class TestKeyringIntegration:
    """Tests for keyring-based secret storage."""

    def test_encryption_key_from_keyring(self, monkeypatch):
        """When keyring has the key, config.encryption_key should return it."""
        import config as config_mod

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "test-fernet-key-base64=="
        monkeypatch.setattr(config_mod, "_keyring", mock_keyring)
        monkeypatch.delenv("GHOSTBACKUP_ENCRYPTION_KEY", raising=False)

        cfg = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
        assert cfg.encryption_key == b"test-fernet-key-base64=="
        mock_keyring.get_password.assert_called_with("GhostBackup", "encryption_key")

    def test_encryption_key_env_fallback(self, monkeypatch):
        """When keyring is None (unavailable), fall back to env var."""
        import config as config_mod

        monkeypatch.setattr(config_mod, "_keyring", None)
        monkeypatch.setenv("GHOSTBACKUP_ENCRYPTION_KEY", "env-key-value")

        cfg = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
        assert cfg.encryption_key == b"env-key-value"

    def test_smtp_password_from_keyring(self, monkeypatch):
        """SMTP password should be loaded from keyring when available."""
        import config as config_mod

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "smtp-secret"
        monkeypatch.setattr(config_mod, "_keyring", mock_keyring)
        monkeypatch.delenv("GHOSTBACKUP_SMTP_PASSWORD", raising=False)

        cfg = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
        assert cfg.smtp_password == "smtp-secret"

    def test_key_storage_method_keyring(self, monkeypatch):
        """key_storage_method should return 'keyring' when keyring is active."""
        import config as config_mod

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "some-key"
        monkeypatch.setattr(config_mod, "_keyring", mock_keyring)

        cfg = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
        assert cfg.key_storage_method == "keyring"

    def test_key_storage_method_env(self, monkeypatch):
        """key_storage_method should return 'env' when keyring is unavailable."""
        import config as config_mod
        monkeypatch.setattr(config_mod, "_keyring", None)

        cfg = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
        assert cfg.key_storage_method == "env"
```

Run: `.venv/bin/python -m pytest backend/tests/test_config.py::TestKeyringIntegration -v`
Expected: FAIL (no `_keyring` attribute, no `key_storage_method` property)

- [ ] **Step 3: Implement keyring support in config.py**

Add near the top of `config.py` (after existing imports, around line 18):

```python
# ── Keyring (optional — Windows Credential Manager) ──────────────────────────
_keyring = None
try:
    import keyring as _keyring
    logger.info("Keyring available — secrets can use Windows Credential Manager")
except ImportError:
    logger.info("Keyring not installed — using environment variables for secrets")
```

Replace the secrets section in `ConfigManager` (lines 131-156):

```python
    # ── Secrets (keyring first, env var fallback) ─────────────────────────────

    @staticmethod
    def _get_secret(keyring_username: str, env_var: str) -> str:
        """Read a secret from keyring (if available), else from env var."""
        if _keyring:
            try:
                val = _keyring.get_password("GhostBackup", keyring_username)
                if val:
                    return val
            except Exception:
                pass  # keyring backend unavailable — fall through to env
        return os.getenv(env_var, "")

    @staticmethod
    def save_secret(keyring_username: str, value: str) -> bool:
        """Save a secret to keyring. Returns True if saved, False if keyring unavailable."""
        if _keyring:
            try:
                _keyring.set_password("GhostBackup", keyring_username, value)
                return True
            except Exception:
                return False
        return False

    @property
    def key_storage_method(self) -> str:
        """Return 'keyring' if keyring is active and has the encryption key, else 'env'."""
        if _keyring:
            try:
                if _keyring.get_password("GhostBackup", "encryption_key"):
                    return "keyring"
            except Exception:
                pass
        return "env"

    @property
    def smtp_password(self) -> str:
        return self._get_secret("smtp_password", "GHOSTBACKUP_SMTP_PASSWORD")

    @property
    def encryption_key(self) -> Optional[bytes]:
        """
        Encryption key loaded from keyring or GHOSTBACKUP_ENCRYPTION_KEY env var.
        Returns bytes if set, None otherwise. Never read from config.yaml.
        """
        raw = self._get_secret("encryption_key", "GHOSTBACKUP_ENCRYPTION_KEY")
        return raw.encode() if raw else None

    @property
    def hkdf_salt(self) -> bytes:
        """
        Per-installation HKDF salt from keyring or GHOSTBACKUP_HKDF_SALT env var.
        Falls back to the legacy hardcoded salt for backward compatibility.
        """
        raw = self._get_secret("hkdf_salt", "GHOSTBACKUP_HKDF_SALT")
        if raw:
            return raw.encode()
        return b"ghostbackup-stream-v1"
```

- [ ] **Step 4: Run keyring tests**

Run: `.venv/bin/python -m pytest backend/tests/test_config.py::TestKeyringIntegration -v`
Expected: 5 tests PASS

- [ ] **Step 5: Add key_storage to /health endpoint**

In `backend/api.py`, in the `health()` function (around line 654), add to the return dict:

```python
        "key_storage":       cfg.key_storage_method,
```

- [ ] **Step 6: Add key storage indicator to Settings UI**

In `src/pages/Settings.jsx`, in the Encryption card (around line 290), after the existing description div, add:

```jsx
        {health?.key_storage && (
          <div className="text-sm mb-12" style={{
            color: health.key_storage === "keyring" ? "var(--green)" : "var(--text-secondary)",
            display: "flex", alignItems: "center", gap: 6,
          }}>
            <span>{health.key_storage === "keyring" ? "🔒" : "📄"}</span>
            Key Storage: {health.key_storage === "keyring"
              ? "Windows Credential Manager"
              : "Environment File (.env.local)"}
          </div>
        )}
```

- [ ] **Step 7: Run full backend tests**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/api.py src/pages/Settings.jsx backend/tests/test_config.py
git commit -m "feat: add keyring support for encryption key protection (Windows Credential Manager)"
```

---

## Task 3: Startup Self-Check

**Files:**
- Modify: `backend/syncer.py:589-657`
- Modify: `backend/api.py:111-170`
- Test: `backend/tests/test_syncer_verify.py`

- [ ] **Step 1: Write failing test for verify_files()**

Add to `backend/tests/test_syncer_verify.py`:

```python
class TestVerifyFiles:
    """Tests for verify_files() — subset verification for spot checks."""

    def test_verify_specific_files_all_ok(self, tmp_path):
        ssd = tmp_path / "ssd"
        ssd.mkdir()
        backup_file = ssd / "doc.txt"
        backup_file.write_bytes(b"hello world")
        file_hash = _hash_file(backup_file)

        cfg = _make_config(ssd_path=str(ssd))
        mani = MagicMock()
        s = LocalSyncer(config=cfg, manifest=mani)

        file_records = [
            {"backup_path": str(backup_file), "xxhash": file_hash, "name": "doc.txt"}
        ]
        result = s.verify_files(file_records)
        assert result["verified"] == 1
        assert result["failed"] == 0
        assert result["missing"] == 0

    def test_verify_specific_files_missing(self, tmp_path):
        ssd = tmp_path / "ssd"
        ssd.mkdir()

        cfg = _make_config(ssd_path=str(ssd))
        mani = MagicMock()
        s = LocalSyncer(config=cfg, manifest=mani)

        file_records = [
            {"backup_path": str(ssd / "gone.txt"), "xxhash": "abc123", "name": "gone.txt"}
        ]
        result = s.verify_files(file_records)
        assert result["verified"] == 0
        assert result["missing"] == 1

    def test_verify_specific_files_corrupt(self, tmp_path):
        ssd = tmp_path / "ssd"
        ssd.mkdir()
        backup_file = ssd / "doc.txt"
        backup_file.write_bytes(b"corrupted content")

        cfg = _make_config(ssd_path=str(ssd))
        mani = MagicMock()
        s = LocalSyncer(config=cfg, manifest=mani)

        file_records = [
            {"backup_path": str(backup_file), "xxhash": "wrong_hash", "name": "doc.txt"}
        ]
        result = s.verify_files(file_records)
        assert result["failed"] == 1

    def test_verify_empty_list(self, tmp_path):
        cfg = _make_config(ssd_path=str(tmp_path))
        mani = MagicMock()
        s = LocalSyncer(config=cfg, manifest=mani)

        result = s.verify_files([])
        assert result["verified"] == 0
        assert result["failed"] == 0
        assert result["missing"] == 0
```

Run: `.venv/bin/python -m pytest backend/tests/test_syncer_verify.py::TestVerifyFiles -v`
Expected: FAIL (`verify_files` not defined)

- [ ] **Step 2: Implement verify_files() in syncer.py**

Add after `verify_backups()` (around line 657) in `backend/syncer.py`:

```python
    def verify_files(self, file_records: list[dict]) -> dict:
        """
        Verify a specific list of file records against the SSD.
        Used for startup spot-checks and targeted verification.
        Returns {verified, failed, missing, errors}.
        """
        verified = 0
        failed   = 0
        missing  = 0
        errors   = []
        chunk    = self._config.chunk_size_bytes

        for row in file_records:
            bp   = row.get("backup_path", "")
            xh   = row.get("xxhash", "")
            name = row.get("name", "")

            bp_path = Path(bp)
            if not bp_path.exists():
                missing += 1
                errors.append({"file": name, "error": "Backup file missing from SSD"})
                continue

            try:
                if self._crypto.enabled:
                    actual_hash = self._crypto.decrypt_and_hash(bp_path)
                else:
                    actual_hash = _hash_file(bp_path, chunk)

                if actual_hash != xh:
                    failed += 1
                    errors.append({
                        "file":  name,
                        "error": f"Hash mismatch (expected={xh[:8]}… got={actual_hash[:8]}…)",
                    })
                else:
                    verified += 1
            except (OSError, RuntimeError) as e:
                failed += 1
                errors.append({"file": name, "error": f"Verification error: {e}"})

        return {"verified": verified, "failed": failed, "missing": missing, "errors": errors}
```

- [ ] **Step 3: Run verify_files tests**

Run: `.venv/bin/python -m pytest backend/tests/test_syncer_verify.py::TestVerifyFiles -v`
Expected: 4 tests PASS

- [ ] **Step 4: Add startup spot-check to api.py lifespan**

In `backend/api.py`, add the spot-check function before the `lifespan` function (around line 110):

```python
import random

async def _startup_spot_check(syncer: LocalSyncer, manifest: ManifestDB,
                              reporter: Reporter) -> None:
    """Spot-check 5 random files from the last successful backup at startup."""
    try:
        last_run = manifest.get_latest_successful_run()
        if not last_run:
            logger.info("Startup spot-check: no previous backups — skipping")
            return

        all_files = manifest.get_files(last_run["id"])
        if not all_files:
            return

        sample_size = min(5, len(all_files))
        sample = random.sample(all_files, sample_size)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: syncer.verify_files(sample))

        if result["failed"] or result["missing"]:
            await reporter.alert_and_notify(
                level="critical",
                title="Startup integrity check FAILED",
                body=(
                    f"Spot-checked {sample_size} files from last backup: "
                    f"{result['failed']} corrupt, {result['missing']} missing. "
                    f"Run a full Verify Integrity check immediately."
                ),
                send_email=True,
            )
            logger.error(f"Startup spot-check FAILED: {result}")
        else:
            logger.info(f"Startup spot-check: {result['verified']}/{sample_size} files OK")
    except Exception as e:
        logger.warning(f"Startup spot-check error: {e}")
```

Then in the `lifespan` function, after `logger.info(f"GhostBackup API ready on ...")` (line 144), add:

```python
    # ── Startup spot-check (non-blocking) ────────────────────────────────────
    asyncio.create_task(_startup_spot_check(_syncer, _manifest, _reporter))
```

- [ ] **Step 5: Run full backend tests**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/syncer.py backend/api.py backend/tests/test_syncer_verify.py
git commit -m "feat: add startup spot-check — verifies 5 random files on launch"
```

---

## Task 4: Backup Immutability Window

**Files:**
- Modify: `backend/config.py:57-62` (DEFAULTS), `backend/config.py:361-385` (validation)
- Modify: `backend/syncer.py:661-701` (prune_old_backups)
- Modify: `backend/api.py:985-1010` (prune endpoint)
- Modify: `backend/config/config.yaml.example`
- Test: `backend/tests/test_syncer_utils.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_syncer_utils.py`:

```python
def test_prune_skips_immutable_backups(tmp_path):
    """Backups within the immutable window must not be deleted."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone, timedelta
    from syncer import LocalSyncer

    # File backed up 3 days ago — within 7-day immutable window
    recent_file = tmp_path / "recent.xlsx"
    recent_file.write_bytes(b"important data")
    recent_date = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

    # File backed up 400 days ago — outside immutable window
    old_file = tmp_path / "old.xlsx"
    old_file.write_bytes(b"old data")
    old_date = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()

    cfg = MagicMock()
    cfg.get_enabled_sources.return_value = [{"label": "Accounts"}]
    cfg.secondary_ssd_path    = ""
    cfg.encryption_key        = None
    cfg.encryption_enabled    = False
    cfg.encryption_config_enabled = False
    cfg.immutable_days        = 7

    manifest = MagicMock()
    manifest.get_backup_files_for_prune.return_value = [
        {"backup_path": str(recent_file), "started_at": recent_date},
        {"backup_path": str(old_file),    "started_at": old_date},
    ]

    syncer = LocalSyncer(config=cfg, manifest=manifest)
    result = syncer.prune_old_backups(daily_days=365, weekly_days=2555, guard_days=7)

    assert result["removed"] == 1           # only old file removed
    assert result["immutable_skipped"] == 1 # recent file protected
    assert not old_file.exists()
    assert recent_file.exists()             # still there!


def test_immutable_days_validation():
    """immutable_days must be >= 7."""
    from config import ConfigManager
    from pathlib import Path

    cfg = ConfigManager(config_path=Path("/tmp/nonexistent.yaml"))
    with pytest.raises(ValueError, match="immutable_days"):
        cfg._validate_update({"immutable_days": 3})
```

Run: `.venv/bin/python -m pytest backend/tests/test_syncer_utils.py::test_prune_skips_immutable_backups backend/tests/test_syncer_utils.py::test_immutable_days_validation -v`
Expected: FAIL

- [ ] **Step 2: Add immutable_days to config**

In `backend/config.py` DEFAULTS dict, add to the retention section (after `"guard_days": 7,`):

```python
        "immutable_days":   7,
```

Add the property to `ConfigManager` (after `retention_guard_days`):

```python
    @property
    def immutable_days(self) -> int:
        return self._data.get("retention", {}).get("immutable_days", 7)
```

Add validation to `_validate_update()` (in the validation method):

```python
        if "immutable_days" in updates:
            v = updates["immutable_days"]
            if not isinstance(v, int) or v < 7:
                raise ValueError("immutable_days must be an integer >= 7")
```

Add to the `update()` mapping dict:

```python
            "immutable_days":            ("retention",   "immutable_days"),
```

- [ ] **Step 3: Update prune_old_backups() to return a dict and enforce immutability**

In `backend/syncer.py`, replace `prune_old_backups()` (lines 661-701):

```python
    def prune_old_backups(
        self,
        daily_days: int,
        weekly_days: int,
        guard_days: int,
    ) -> dict:
        """
        Remove backup files older than the retention policy.
        Returns {removed, immutable_skipped} instead of a plain int.
        Backups within the immutable_days window are never deleted.
        """
        guard_cutoff     = datetime.now(timezone.utc) - timedelta(days=guard_days)
        daily_cutoff     = datetime.now(timezone.utc) - timedelta(days=daily_days)
        immutable_cutoff = datetime.now(timezone.utc) - timedelta(
            days=getattr(self._config, "immutable_days", 7)
        )
        removed            = 0
        immutable_skipped  = 0

        for source in self._config.get_enabled_sources():
            label     = source.get("label") or source.get("name", "")
            old_files = self._manifest.get_backup_files_for_prune(
                label, daily_cutoff.isoformat()
            )
            pruned_dates: set[str] = set()
            for f in old_files:
                backed_up = datetime.fromisoformat(
                    f.get("started_at", datetime.now(timezone.utc).isoformat())
                )
                if backed_up > guard_cutoff:
                    continue
                if backed_up > immutable_cutoff:
                    immutable_skipped += 1
                    continue
                bp = Path(f["backup_path"])
                if bp.exists():
                    try:
                        bp.unlink()
                        removed += 1
                        pruned_dates.add(backed_up.strftime("%Y-%m-%d"))
                    except OSError as e:
                        logger.warning(f"Could not prune {bp}: {e}")

            for date_str in pruned_dates:
                next_day = (
                    datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y-%m-%d")
                self._manifest.mark_run_pruned(date_str, next_day)

        logger.info(f"Prune complete — {removed} removed, {immutable_skipped} immutable skipped")
        return {"removed": removed, "immutable_skipped": immutable_skipped}
```

- [ ] **Step 4: Update _do_prune() in api.py to handle the new return dict**

In `backend/api.py`, replace `_do_prune()` (around line 996):

```python
async def _do_prune(cfg: ConfigManager, syncer: LocalSyncer, reporter: Reporter):
    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: syncer.prune_old_backups(
            cfg.retention_daily_days,
            cfg.retention_weekly_days,
            cfg.retention_guard_days,
        ),
    )
    removed   = result["removed"]
    immutable = result["immutable_skipped"]
    msg = f"{removed} old backup files removed from SSD."
    if immutable:
        msg += f" {immutable} files skipped (within immutable window)."
    logger.info(f"Prune complete — {removed} removed, {immutable} immutable skipped")
    reporter.alerts.add("info", "Prune complete", msg)
```

- [ ] **Step 5: Update existing prune tests to expect dict return**

In `backend/tests/test_syncer_utils.py`, update the two existing prune tests.

`test_prune_calls_mark_run_pruned_when_files_deleted` — change:
```python
    assert removed == 1
```
to:
```python
    assert result["removed"] == 1
```
(also rename the variable from `removed` to `result`)

`test_prune_does_not_mark_pruned_when_nothing_deleted` — change:
```python
    assert removed == 0
```
to:
```python
    assert result["removed"] == 0
```
(also rename the variable from `removed` to `result`, and add `cfg.immutable_days = 7`)

- [ ] **Step 6: Add immutable_days to config.yaml.example**

In `backend/config/config.yaml.example`, add after `guard_days: 7`:

```yaml
  immutable_days: 7       # Backups younger than this CANNOT be deleted (minimum 7)
```

- [ ] **Step 7: Run all backend tests**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/config.py backend/syncer.py backend/api.py backend/config/config.yaml.example backend/tests/test_syncer_utils.py
git commit -m "feat: add backup immutability window — prevents deletion of recent backups"
```

---

## Task 5: Restore Drill Reminder (with tracking)

**Files:**
- Modify: `backend/manifest.py:56,165-177`
- Modify: `backend/scheduler.py`
- Modify: `backend/api.py`
- Modify: `src/pages/Settings.jsx`
- Modify: `src/api-client.js`
- Test: `backend/tests/test_manifest.py`

- [ ] **Step 1: Write failing tests for drill methods**

Add to `backend/tests/test_manifest.py`:

```python
class TestRestoreDrills:

    def test_record_drill(self, tmp_path):
        db = ManifestDB(db_path=tmp_path / "test.db")
        drill_id = db.record_drill(restore_run_id=1, notes="Monthly test")
        assert drill_id > 0

    def test_get_last_drill_completion_none(self, tmp_path):
        db = ManifestDB(db_path=tmp_path / "test.db")
        assert db.get_last_drill_completion() is None

    def test_get_last_drill_completion_after_record(self, tmp_path):
        db = ManifestDB(db_path=tmp_path / "test.db")
        db.record_drill(restore_run_id=1)
        result = db.get_last_drill_completion()
        assert result is not None
        assert "T" in result  # ISO format

    def test_get_drill_history(self, tmp_path):
        db = ManifestDB(db_path=tmp_path / "test.db")
        db.record_drill(restore_run_id=1, notes="First")
        db.record_drill(restore_run_id=2, notes="Second")
        history = db.get_drill_history(limit=10)
        assert len(history) == 2
        assert history[0]["notes"] == "Second"  # Most recent first

    def test_schema_v4_migration(self, tmp_path):
        db = ManifestDB(db_path=tmp_path / "test.db")
        version = db._conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version >= 4
```

Run: `.venv/bin/python -m pytest backend/tests/test_manifest.py::TestRestoreDrills -v`
Expected: FAIL

- [ ] **Step 2: Add schema v4 migration and drill methods to manifest.py**

In `backend/manifest.py`, update `_SCHEMA_VERSION` (line 56):

```python
    _SCHEMA_VERSION = 4
```

Add after the v3 migration block (after line 177):

```python
            if current < 4:
                # v4: restore drill tracking
                self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS restore_drills (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        due_date        TEXT NOT NULL,
                        completed_at    TEXT,
                        restore_run_id  INTEGER,
                        notes           TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_drills_due
                        ON restore_drills(due_date DESC);
                """)
                self._conn.execute("UPDATE schema_version SET version = 4")
                self._conn.commit()
                logger.info("DB migrated to schema v4 (restore_drills)")
```

Add drill methods after `get_config_audit()` (after line 399):

```python
    # ── Restore drills ─────────────────────────────────────────────────────────

    def record_drill(self, restore_run_id: int = None, notes: str = "") -> int:
        """Record a completed restore drill. Returns the drill ID."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO restore_drills (due_date, completed_at, restore_run_id, notes)
                   VALUES (?, ?, ?, ?)""",
                (now, now, restore_run_id, notes),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_last_drill_completion(self) -> Optional[str]:
        """ISO timestamp of the most recent completed drill, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT completed_at FROM restore_drills WHERE completed_at IS NOT NULL "
                "ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
        return row["completed_at"] if row else None

    def get_drill_history(self, limit: int = 12) -> list[dict]:
        """Last N drill records for audit display."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM restore_drills ORDER BY completed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 3: Run drill tests**

Run: `.venv/bin/python -m pytest backend/tests/test_manifest.py::TestRestoreDrills -v`
Expected: 5 tests PASS

- [ ] **Step 4: Auto-record drill on restore**

In `backend/api.py`, in the `restore()` endpoint (around line 894-910), after the successful non-dry-run restore result, add:

```python
        # Auto-record as a restore drill for compliance tracking
        manifest.record_drill(
            restore_run_id=req.run_id,
            notes=f"Restore of run #{req.run_id} to {req.destination}",
        )
```

- [ ] **Step 5: Add drill check to scheduler**

In `backend/scheduler.py`, add after `_missed_backup_check()`:

```python
    # ── Restore drill check ──────────────────────────────────────────────────

    _DRILL_DUE_DAYS      = 30
    _DRILL_WARN_DAYS     = 37
    _DRILL_CRITICAL_DAYS = 44
    _drill_alerted_level: Optional[str] = None

    async def _restore_drill_check(self) -> None:
        """Check if a restore drill is overdue and escalate alerts."""
        if not self._reporter or not self._manifest_ref:
            return

        try:
            last = self._manifest_ref.get_last_drill_completion()
            if last:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - last_dt).days
            else:
                # No drill ever — check days since first backup
                first_run = self._manifest_ref.get_latest_successful_run()
                if not first_run:
                    return  # No backups yet
                first_dt = datetime.fromisoformat(first_run["started_at"])
                if first_dt.tzinfo is None:
                    first_dt = first_dt.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - first_dt).days

            if days_since >= self._DRILL_CRITICAL_DAYS and self._drill_alerted_level != "critical":
                self._drill_alerted_level = "critical"
                await self._reporter.alert_and_notify(
                    level="critical",
                    title="Restore drill overdue by 2+ weeks",
                    body=(
                        f"No restore drill completed in {days_since} days. "
                        f"Go to Restore and verify a recent backup immediately. "
                        f"This is a compliance risk."
                    ),
                    send_email=True,
                )
            elif days_since >= self._DRILL_WARN_DAYS and self._drill_alerted_level not in ("warn", "critical"):
                self._drill_alerted_level = "warn"
                await self._reporter.alert_and_notify(
                    level="warn",
                    title="Restore drill overdue by 1 week",
                    body=(
                        f"No restore drill completed in {days_since} days. "
                        f"Go to Restore and verify a recent backup."
                    ),
                    send_email=True,
                )
            elif days_since >= self._DRILL_DUE_DAYS and self._drill_alerted_level is None:
                self._drill_alerted_level = "info"
                self._reporter.alerts.add(
                    "info",
                    "Monthly restore drill due",
                    "Go to Restore and verify a recent backup to confirm recoverability.",
                )
            elif days_since < self._DRILL_DUE_DAYS:
                self._drill_alerted_level = None  # Reset when drill completed

        except Exception as e:
            logger.error(f"Restore drill check error: {e}")
```

Register the job in the `start()` method (alongside the existing missed-backup job):

```python
        self._scheduler.add_job(
            self._async_wrapper(self._restore_drill_check),
            "interval",
            hours=24,
            id="drill_check",
            name="Restore drill check",
            replace_existing=True,
        )
```

- [ ] **Step 6: Add drill status API endpoint and frontend**

In `backend/api.py`, add the endpoint:

```python
@app.get("/settings/drill-status")
async def drill_status(manifest: ManifestDB = Depends(get_manifest)):
    last = manifest.get_last_drill_completion()
    history = manifest.get_drill_history(limit=12)
    days_since = None
    next_due = None
    if last:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - last_dt).days
        next_due = (last_dt + timedelta(days=30)).isoformat()
    return {
        "last_completed": last,
        "days_since_last": days_since,
        "next_due": next_due,
        "overdue": days_since is not None and days_since >= 30,
        "history": history,
    }
```

In `src/api-client.js`, add to the `api` object:

```javascript
  drillStatus:     ()            => request("GET",    "/settings/drill-status"),
```

In `src/pages/Settings.jsx`, add a Restore Drill card after the Verify Integrity card:

```jsx
      {/* Restore Drill */}
      <div className="card">
        <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>🧪</span> Restore Drill
        </div>
        <div className="text-sm text-secondary mb-12">
          Restore drills are automatically recorded when you restore files. Run a test restore monthly to confirm backup recoverability.
        </div>
        {drillStatus ? (
          <div className="text-sm" style={{ lineHeight: 1.8 }}>
            <div>Last completed: <strong>{drillStatus.last_completed
              ? new Date(drillStatus.last_completed).toLocaleDateString()
              : "Never"}</strong>
              {drillStatus.days_since_last != null && ` (${drillStatus.days_since_last} days ago)`}
            </div>
            <div>Next due: <strong>{drillStatus.next_due
              ? new Date(drillStatus.next_due).toLocaleDateString()
              : "After first restore"}</strong></div>
            <div style={{ color: drillStatus.overdue ? "var(--red)" : "var(--green)" }}>
              Status: {drillStatus.overdue ? "Overdue" : "On track"}
            </div>
          </div>
        ) : (
          <div className="text-sm text-secondary">Loading...</div>
        )}
      </div>
```

Add the state and fetch at the top of the Settings component:

```javascript
const [drillStatus, setDrillStatus] = useState(null);

useEffect(() => {
  api.drillStatus().then(setDrillStatus).catch(() => {});
}, []);
```

- [ ] **Step 7: Run full backend tests**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/manifest.py backend/scheduler.py backend/api.py src/pages/Settings.jsx src/api-client.js backend/tests/test_manifest.py
git commit -m "feat: add restore drill tracking with escalating reminders"
```

---

## Task 6: Structured Error Codes

**Files:**
- Create: `backend/errors.py`
- Modify: `backend/api.py`
- Modify: `src/api-client.js:97-105`
- Modify: `SETUP.md`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Create errors.py**

```python
"""
errors.py — Structured error codes for GhostBackup API.

Each error has a code (GB-Exxx), a human-readable message, and a fix suggestion.
The fix text is shown in the UI and documented in SETUP.md.
"""

from dataclasses import dataclass
from fastapi import HTTPException


@dataclass(frozen=True)
class GBError:
    code: str
    message: str
    fix: str = ""


# ── Error Registry ────────────────────────────────────────────────────────────

ERRORS: dict[str, GBError] = {
    # Encryption
    "GB-E001": GBError("GB-E001", "Encryption key not set",
                       "Set GHOSTBACKUP_ENCRYPTION_KEY via Settings or .env.local"),
    "GB-E002": GBError("GB-E002", "Encryption initialization failed",
                       "Verify the key is a valid Fernet key (base64-encoded, 44 chars)"),
    "GB-E003": GBError("GB-E003", "Key fingerprint mismatch on restore",
                       "The file was encrypted with a different key. Provide the original key."),

    # SSD
    "GB-E010": GBError("GB-E010", "Primary SSD not connected",
                       "Connect the backup drive and verify the path in Settings"),
    "GB-E011": GBError("GB-E011", "SSD free space critically low",
                       "Prune old backups from Settings or connect a larger drive"),

    # Backup
    "GB-E020": GBError("GB-E020", "Backup already in progress",
                       "Wait for the current run to finish or stop it from the dashboard"),
    "GB-E021": GBError("GB-E021", "Source folder not found",
                       "Verify the source path exists and is accessible"),
    "GB-E022": GBError("GB-E022", "Circuit breaker triggered",
                       "Too many file failures in one library. Check file permissions."),
    "GB-E023": GBError("GB-E023", "Backup job timed out",
                       "Increase max_job_minutes in config or reduce source size"),

    # Config
    "GB-E030": GBError("GB-E030", "Invalid configuration value",
                       "Check field constraints in Settings or SETUP.md"),
    "GB-E031": GBError("GB-E031", "Retention below compliance minimum",
                       "weekly_days cannot be less than compliance_years x 365"),
    "GB-E032": GBError("GB-E032", "Cannot delete immutable backup",
                       "Backups within the immutable window cannot be pruned"),

    # Restore
    "GB-E040": GBError("GB-E040", "Restore from failed run rejected",
                       "Select a successful or partial run instead"),
    "GB-E041": GBError("GB-E041", "No files found for restore",
                       "The selected run has no transferable files matching your criteria"),
    "GB-E042": GBError("GB-E042", "Path traversal blocked",
                       "The destination path attempted to escape the target directory"),

    # SMTP
    "GB-E050": GBError("GB-E050", "SMTP test failed",
                       "Verify host, port, credentials, and TLS settings in Settings"),

    # System
    "GB-E060": GBError("GB-E060", "Cannot verify during backup",
                       "Wait for the backup to finish before running verification"),
    "GB-E061": GBError("GB-E061", "Cannot prune during backup",
                       "Wait for the backup to finish before pruning"),
}


def raise_gb(code: str, status: int = 400, detail_override: str = None) -> None:
    """Raise an HTTPException with a structured error body."""
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

- [ ] **Step 2: Write test for structured errors**

Add to `backend/tests/test_api.py`:

```python
class TestStructuredErrors:
    def test_error_response_has_code_field(self, client):
        """Error responses should include a GB-Exxx code."""
        # Trigger a known error: restore from nonexistent run
        r = client.post("/restore", json={
            "run_id": 99999, "destination": "/tmp/restore", "dry_run": False
        })
        assert r.status_code == 404
        data = r.json()
        detail = data.get("detail", data)
        if isinstance(detail, dict):
            assert "code" in detail
            assert detail["code"].startswith("GB-E")
            assert "fix" in detail

    def test_verify_during_backup_returns_error_code(self, client):
        client._api._active_run = {"status": "running"}
        r = client.post("/verify")
        assert r.status_code == 409
        data = r.json()
        detail = data.get("detail", data)
        if isinstance(detail, dict):
            assert detail["code"] == "GB-E060"
```

- [ ] **Step 3: Replace key HTTPException calls in api.py with raise_gb()**

Add import at the top of `api.py`:

```python
from errors import raise_gb
```

Replace the following calls (find-and-replace each one):

| Old | New |
|-----|-----|
| `raise HTTPException(409, "A backup run is already in progress")` | `raise_gb("GB-E020", 409)` |
| `raise HTTPException(404, f"Run #{req.run_id} not found")` | `raise HTTPException(404, {"code": "GB-E040", "message": f"Run #{req.run_id} not found", "fix": "Check the run ID in the Logs page"})` |
| `raise HTTPException(400, "Cannot restore from a failed run")` | `raise_gb("GB-E040")` |
| `raise HTTPException(404, "No files found matching the restore criteria")` | `raise_gb("GB-E041", 404)` |
| `raise HTTPException(400, "Path traversal detected in destination")` | `raise_gb("GB-E042")` |
| `raise HTTPException(409, "Cannot verify while a backup is running")` | `raise_gb("GB-E060", 409)` |
| `raise HTTPException(409, "Cannot prune while a backup is running")` | `raise_gb("GB-E061", 409)` |
| `raise HTTPException(500, f"SMTP test failed: {e}")` | `raise_gb("GB-E050", 500, f"SMTP test failed: {e}")` |

- [ ] **Step 4: Update frontend error handling for structured errors**

In `src/api-client.js`, update the error parsing (around line 97-105):

```javascript
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail?.message || j.detail || j.message || detail;
    } catch {
      // Response body was not JSON — use statusText as-is
    }
```

- [ ] **Step 5: Add error code reference to SETUP.md**

Add before the "Generating a New Encryption Key" section:

```markdown
---

## Error Code Reference

| Code | Meaning | Fix |
|------|---------|-----|
| GB-E001 | Encryption key not set | Set GHOSTBACKUP_ENCRYPTION_KEY via Settings or .env.local |
| GB-E002 | Encryption initialization failed | Verify the key is a valid Fernet key (base64, 44 chars) |
| GB-E003 | Key fingerprint mismatch on restore | File was encrypted with a different key |
| GB-E010 | Primary SSD not connected | Connect the backup drive and check path in Settings |
| GB-E011 | SSD free space critically low | Prune old backups or connect a larger drive |
| GB-E020 | Backup already in progress | Wait for the current run to finish |
| GB-E021 | Source folder not found | Verify the source path exists |
| GB-E022 | Circuit breaker triggered | Too many file failures — check permissions |
| GB-E023 | Backup job timed out | Increase max_job_minutes in config |
| GB-E030 | Invalid configuration value | Check field constraints in SETUP.md |
| GB-E031 | Retention below compliance minimum | weekly_days must be >= compliance_years x 365 |
| GB-E032 | Cannot delete immutable backup | Backups within immutable window are protected |
| GB-E040 | Restore from failed run rejected | Select a successful or partial run |
| GB-E041 | No files found for restore | Run has no matching files |
| GB-E042 | Path traversal blocked | Destination path tried to escape target directory |
| GB-E050 | SMTP test failed | Verify host, port, credentials, TLS in Settings |
| GB-E060 | Cannot verify during backup | Wait for backup to finish |
| GB-E061 | Cannot prune during backup | Wait for backup to finish |
```

- [ ] **Step 6: Update existing tests that check for old error formats**

Some existing tests check `r.json()["detail"]` as a string. These now get a dict. Update tests that rely on specific error messages to handle both formats. For most tests, the status code check is sufficient.

- [ ] **Step 7: Run full backend tests**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS (fix any assertion failures from error format changes)

- [ ] **Step 8: Commit**

```bash
git add backend/errors.py backend/api.py src/api-client.js SETUP.md backend/tests/test_api.py
git commit -m "feat: add structured error codes (GB-Exxx) with fix suggestions"
```

---

## Task 7: Deep Health Endpoint

**Files:**
- Modify: `backend/api.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_api.py`:

```python
class TestHealthDeep:
    def test_deep_health_returns_all_fields(self, client):
        r = client.get("/health/deep")
        assert r.status_code == 200
        data = r.json()
        expected_keys = {
            "ssd_connected", "ssd_free_gb", "last_backup_age_hours",
            "last_backup_status", "encryption_active", "key_storage",
            "manifest_ok", "manifest_size_mb", "spot_check",
            "scheduler_running", "next_backup", "restore_drill_overdue",
            "restore_drill_days_remaining", "version", "overall",
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_deep_health_overall_field(self, client):
        r = client.get("/health/deep")
        assert r.json()["overall"] in ("healthy", "degraded", "unhealthy")

    def test_deep_health_spot_check_structure(self, client):
        r = client.get("/health/deep")
        sc = r.json()["spot_check"]
        assert "checked" in sc
        assert "passed" in sc
        assert "failed" in sc
```

Run: `.venv/bin/python -m pytest backend/tests/test_api.py::TestHealthDeep -v`
Expected: FAIL (404 — endpoint doesn't exist)

- [ ] **Step 2: Implement /health/deep endpoint**

Add to `backend/api.py` after the existing `/health` endpoint:

```python
@app.get("/health/deep")
@_limiter.limit("10/minute")
async def health_deep(request: Request,
                      cfg: ConfigManager = Depends(provide_config),
                      manifest: ManifestDB = Depends(get_manifest),
                      syncer: LocalSyncer = Depends(get_syncer),
                      scheduler: BackupScheduler = Depends(get_scheduler),
                      reporter: Reporter = Depends(get_reporter)):
    """
    Comprehensive health check for external monitoring.
    Returns SSD status, last backup age, encryption, integrity spot-check,
    scheduler state, drill status, and overall assessment.
    """
    # SSD
    ssd = get_ssd_status(cfg.ssd_path)
    ssd_connected = ssd.get("status") == "ok"
    ssd_free_gb = ssd.get("available_gb", 0)

    secondary_ssd = get_ssd_status(cfg.secondary_ssd_path) if cfg.secondary_ssd_path else None
    secondary_connected = secondary_ssd.get("status") == "ok" if secondary_ssd else None

    # Last backup
    last_run = manifest.get_latest_successful_run()
    last_age_hours = None
    last_status = None
    if last_run:
        last_dt = datetime.fromisoformat(last_run["started_at"])
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        last_age_hours = round(
            (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600, 1
        )
        last_status = last_run["status"]

    # Spot-check (up to 5 random files)
    spot = {"checked": 0, "passed": 0, "failed": 0}
    try:
        if last_run:
            all_files = manifest.get_files(last_run["id"])
            if all_files:
                sample = random.sample(all_files, min(5, len(all_files)))
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: syncer.verify_files(sample)
                )
                spot = {
                    "checked": result["verified"] + result["failed"] + result["missing"],
                    "passed": result["verified"],
                    "failed": result["failed"] + result["missing"],
                }
    except Exception as e:
        logger.warning(f"Deep health spot-check error: {e}")

    # Manifest
    manifest_ok = True
    manifest_size_mb = 0
    try:
        manifest_size_mb = round(manifest.db_path.stat().st_size / (1024 * 1024), 1)
    except Exception:
        manifest_ok = False

    # Restore drill
    drill_last = manifest.get_last_drill_completion()
    drill_overdue = False
    drill_days_remaining = None
    if drill_last:
        drill_dt = datetime.fromisoformat(drill_last)
        if drill_dt.tzinfo is None:
            drill_dt = drill_dt.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - drill_dt).days
        drill_overdue = days_since >= 30
        drill_days_remaining = max(0, 30 - days_since)

    # Overall assessment
    overall = "healthy"
    if not ssd_connected or not syncer.encryption_active or spot["failed"] > 0:
        overall = "unhealthy"
    elif (last_age_hours and last_age_hours > 36) or drill_overdue or \
         (secondary_connected is False):
        overall = "degraded"

    return {
        "ssd_connected":               ssd_connected,
        "ssd_free_gb":                 ssd_free_gb,
        "secondary_ssd_connected":     secondary_connected,
        "last_backup_age_hours":       last_age_hours,
        "last_backup_status":          last_status,
        "encryption_active":           syncer.encryption_active if syncer else False,
        "key_storage":                 cfg.key_storage_method,
        "manifest_ok":                 manifest_ok,
        "manifest_size_mb":            manifest_size_mb,
        "spot_check":                  spot,
        "scheduler_running":           scheduler.is_running() if scheduler else False,
        "next_backup":                 scheduler.next_run_time() if scheduler else None,
        "restore_drill_overdue":       drill_overdue,
        "restore_drill_days_remaining": drill_days_remaining,
        "version":                     app.version,
        "overall":                     overall,
    }
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest backend/tests/test_api.py::TestHealthDeep -v`
Expected: 3 tests PASS

- [ ] **Step 4: Run full backend tests**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api.py backend/tests/test_api.py
git commit -m "feat: add /health/deep endpoint for external monitoring"
```

---

## Task 8: Documentation & Version Bump

**Files:**
- Modify: `package.json`
- Modify: `backend/api.py` (version string)
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Bump version to 3.0.0**

In `package.json`: change `"version": "2.9.1"` to `"version": "3.0.0"`
In `backend/api.py`: change `version="2.9.1"` to `version="3.0.0"`

- [ ] **Step 2: Update CHANGELOG.md**

Add at the top (after the header line):

```markdown
## v3.0.0 — Security, Monitoring & Compliance

### Security
- **Keyring encryption key protection** (`config.py`): Secrets migrate to Windows Credential Manager via `keyring` library. Env var fallback for CI/headless. Key storage method shown in Settings.
- **Backup immutability window** (`syncer.py`, `config.py`): Backups within `immutable_days` (default 7) cannot be deleted by any prune operation. Configurable, minimum 7 days.

### Monitoring
- **Startup self-check** (`api.py`): On launch, 5 random files from the last backup are verified. Critical alert if any are corrupt or missing.
- **Deep health endpoint** (`api.py`): `GET /health/deep` returns SSD status, backup age, encryption, spot-check, scheduler, drill status, and overall assessment for external monitoring tools.

### Compliance
- **Restore drill tracking** (`manifest.py`, `scheduler.py`): Every non-dry-run restore is automatically recorded. Scheduler escalates reminders: info at 30 days, warn + email at 37, critical + email at 44 days. Drill history viewable in Settings.

### Developer Experience
- **Structured error codes** (`errors.py`): All API errors return `{code, message, fix}`. Codes documented in SETUP.md. Frontend displays actionable fix suggestions.
- **E2E integration test** (`test_e2e_pipeline.py`): Full backup → verify → restore → byte-compare pipeline test with real encryption.

### Testing
- Total tests: 338 + new E2E and unit tests

---
```

- [ ] **Step 3: Update README.md features table**

Add these rows to the features table:

```markdown
| 🔐 Key Protection | Encryption keys stored in Windows Credential Manager (keyring). Automatic migration from `.env.local`. Env var fallback for CI. |
| 🚀 Startup Self-Check | On launch, 5 random backup files are verified against the manifest. Critical alert on corruption. |
| 🔒 Immutable Backups | Backups within the immutable window (default 7 days) cannot be deleted by any operation. |
| 🧪 Restore Drill Tracking | Every restore is logged. Escalating reminders if no drill in 30/37/44 days. Audit-ready history. |
| 🏥 Deep Health Check | `GET /health/deep` returns comprehensive system status for external uptime monitors. |
| 🔢 Structured Errors | API errors include codes (GB-Exxx) with fix suggestions. Reference table in SETUP.md. |
```

Update the API Endpoints table — add:

```markdown
| GET | /health/deep | Comprehensive health check for monitoring tools |
| GET | /settings/drill-status | Restore drill status and history |
```

- [ ] **Step 4: Run all tests one final time**

Run: `.venv/bin/python -m pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add package.json backend/api.py CHANGELOG.md README.md
git commit -m "docs: v3.0.0 changelog, readme, and version bump"
```

---

## Execution Checklist

| Task | Feature | Depends On | Est. |
|------|---------|-----------|------|
| 1 | E2E integration test | None | 10 min |
| 2 | Keyring encryption | None | 15 min |
| 3 | Startup self-check | Task 1 (verify_files) | 10 min |
| 4 | Immutability window | None | 10 min |
| 5 | Restore drill tracking | None | 15 min |
| 6 | Structured error codes | None | 15 min |
| 7 | Deep health endpoint | Tasks 3, 5 | 10 min |
| 8 | Docs & version bump | All above | 5 min |
