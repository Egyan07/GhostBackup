"""
test_e2e_pipeline.py — End-to-end integration tests for the GhostBackup pipeline.

Exercises the full backup cycle with real files, real AES-256-GCM encryption,
and a real SQLite manifest database. No mocks for the core path.

Test coverage:
  - Full backup cycle: scan -> copy -> verify -> restore -> byte-for-byte match
  - Incremental backup: second run skips unchanged files
  - Key fingerprint tracking in manifest file records
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from config import ConfigManager
from manifest import ManifestDB
from syncer import LocalSyncer, _STREAM_MAGIC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_files(root: Path) -> list[Path]:
    """
    Create 8 test files of varying sizes across nested subdirectories.
    Also creates an excluded file (~$lockfile.xlsx) that should be skipped.
    Returns the list of paths that should be detected by scan (excludes excluded files).
    """
    files = []

    # Flat files
    for name, size in [
        ("small.txt", 1024),            # 1 KB
        ("medium.bin", 50 * 1024),       # 50 KB
        ("large.dat", 500 * 1024),       # 500 KB
        ("report.xlsx", 200 * 1024),     # 200 KB
    ]:
        p = root / name
        p.write_bytes(os.urandom(size))
        files.append(p)

    # Nested subdirectory
    sub = root / "clients" / "acme"
    sub.mkdir(parents=True, exist_ok=True)
    for name, size in [
        ("invoice.pdf", 100 * 1024),     # 100 KB
        ("ledger.csv", 10 * 1024),       # 10 KB
    ]:
        p = sub / name
        p.write_bytes(os.urandom(size))
        files.append(p)

    # Deeper nesting
    deep = root / "archive" / "2025" / "Q4"
    deep.mkdir(parents=True, exist_ok=True)
    for name, size in [
        ("annual_accounts.pdf", 1024 * 1024),  # 1 MB
        ("notes.txt", 2048),                     # 2 KB
    ]:
        p = deep / name
        p.write_bytes(os.urandom(size))
        files.append(p)

    # Excluded file (Office lock file pattern ~$*)
    excluded = root / "~$lockfile.xlsx"
    excluded.write_bytes(b"lock data")

    return files


def _write_test_config(config_path: Path, source_path: Path, ssd_path: Path) -> None:
    """Write a minimal config YAML suitable for E2E testing."""
    import yaml
    cfg = {
        "ssd_path": str(ssd_path),
        "secondary_ssd_path": "",
        "encryption": {"enabled": True},
        "schedule": {
            "time": "08:00",
            "timezone": "Europe/London",
            "max_job_minutes": 240,
            "retry_count": 3,
            "retry_delay_minutes": 30,
        },
        "performance": {
            "concurrency": 1,
            "max_file_size_gb": 5,
            "chunk_size_mb": 1,
        },
        "backup": {
            "verify_checksums": True,
            "version_count": 5,
            "exclude_patterns": [
                "~$*", "*.tmp", "Thumbs.db", ".DS_Store",
                "desktop.ini", "*.lnk",
            ],
        },
        "retention": {
            "daily_days": 365,
            "weekly_days": 2555,
            "compliance_years": 7,
            "guard_days": 7,
        },
        "circuit_breaker_threshold": 0.05,
        "watcher": {"debounce_seconds": 15, "cooldown_seconds": 120},
        "smtp": {"host": "localhost", "port": 587, "use_tls": True, "user": "", "recipients": []},
        "logging": {"level": "DEBUG", "retention_days": 365, "log_dir": "logs"},
        "sources": [
            {"label": "TestSource", "path": str(source_path), "enabled": True},
        ],
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def e2e_env(tmp_path, monkeypatch):
    """
    Set up a complete E2E environment:
      - temp source dir with test files
      - temp SSD destination dir
      - temp manifest DB
      - real Fernet key + HKDF salt in env
      - real ConfigManager, ManifestDB, LocalSyncer
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    ssd_dir = tmp_path / "ssd"
    ssd_dir.mkdir()
    restore_dir = tmp_path / "restored"
    config_path = tmp_path / "config" / "config.yaml"
    db_path = tmp_path / "manifest.db"

    # Create test files
    expected_files = _create_test_files(source_dir)

    # Generate real encryption key
    fernet_key = Fernet.generate_key()
    monkeypatch.setenv("GHOSTBACKUP_ENCRYPTION_KEY", fernet_key.decode())
    monkeypatch.setenv("GHOSTBACKUP_HKDF_SALT", "e2e-test-salt-value")

    # Write config
    _write_test_config(config_path, source_dir, ssd_dir)

    # Instantiate real components
    cfg = ConfigManager(config_path=config_path)
    manifest = ManifestDB(db_path=db_path)
    syncer = LocalSyncer(config=cfg, manifest=manifest)

    yield {
        "source_dir": source_dir,
        "ssd_dir": ssd_dir,
        "restore_dir": restore_dir,
        "config": cfg,
        "manifest": manifest,
        "syncer": syncer,
        "expected_files": expected_files,
        "fernet_key": fernet_key,
    }

    manifest.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestE2EPipeline:
    """End-to-end integration tests for the full backup pipeline."""

    def test_e2e_full_backup_cycle(self, e2e_env):
        """
        Happy path: scan -> copy -> verify -> restore, all with real encryption.
        Restored files must match originals byte-for-byte.
        """
        syncer = e2e_env["syncer"]
        manifest = e2e_env["manifest"]
        source_dir = e2e_env["source_dir"]
        restore_dir = e2e_env["restore_dir"]
        expected_files = e2e_env["expected_files"]

        source = {"label": "TestSource", "path": str(source_dir)}

        # ── Step 1: Scan ──────────────────────────────────────────────────
        changed, skipped = syncer.scan_source(source, force_full=True)

        # All non-excluded files detected as changed
        assert len(changed) == len(expected_files), (
            f"Expected {len(expected_files)} changed files, got {len(changed)}"
        )
        # The excluded ~$lockfile.xlsx should be in the skipped count
        assert skipped >= 1, "Expected at least 1 skipped (excluded) file"

        # ── Step 2: Copy (encrypted) ─────────────────────────────────────
        run_id = manifest.create_run(full_backup=True)
        backup_paths = []

        for file_meta in changed:
            bp = syncer.copy_file(file_meta, run_id)
            backup_paths.append(bp)
            manifest.record_file(
                run_id, file_meta, bp,
                key_fingerprint=syncer.key_fingerprint,
            )

        manifest.flush()

        # All destination files exist and start with GBENC1 magic header
        for bp in backup_paths:
            bp_path = Path(bp)
            assert bp_path.exists(), f"Backup file missing: {bp}"
            header = bp_path.read_bytes()[:6]
            assert header == _STREAM_MAGIC, (
                f"Expected GBENC1 header, got {header!r} in {bp}"
            )

        # Finalize the run
        started_at = datetime.now(timezone.utc).isoformat()
        manifest.finalize_run(run_id, {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "files_transferred": len(changed),
            "files_skipped": skipped,
            "files_failed": 0,
            "bytes_transferred": sum(f["size"] for f in changed),
        })

        # ── Step 3: Verify ────────────────────────────────────────────────
        result = syncer.verify_backups("TestSource")
        assert result["verified"] == len(expected_files), (
            f"Expected {len(expected_files)} verified, got {result['verified']}"
        )
        assert result["failed"] == 0, f"Corrupt files: {result['errors']}"
        assert result["missing"] == 0, f"Missing files: {result['errors']}"

        # ── Step 4: Restore ───────────────────────────────────────────────
        file_records = manifest.get_files(run_id)
        assert len(file_records) == len(expected_files)

        restore_result = syncer.restore_files(file_records, str(restore_dir))
        assert restore_result["restored"] == len(expected_files), (
            f"Expected {len(expected_files)} restored, got {restore_result}"
        )
        assert restore_result["failed"] == 0, f"Restore failures: {restore_result['errors']}"

        # Byte-for-byte comparison of restored files against originals
        for orig in expected_files:
            rel = orig.relative_to(source_dir)
            restored = restore_dir / rel
            assert restored.exists(), f"Restored file missing: {restored}"
            assert orig.read_bytes() == restored.read_bytes(), (
                f"Content mismatch for {rel}"
            )

        # ── Step 5: Verify manifest DB records ────────────────────────────
        run = manifest.get_run(run_id)
        assert run is not None
        assert run["status"] == "success"
        assert run["files_transferred"] == len(expected_files)

        # Hash cache entries exist for all source files
        for orig in expected_files:
            cached = manifest.get_file_hash(str(orig))
            assert cached is not None, f"No hash cache for {orig}"
            assert "xxhash" in cached
            assert cached["size"] == orig.stat().st_size

    def test_e2e_incremental_skips_unchanged(self, e2e_env):
        """
        Run backup twice without modifying files.
        The second scan (non-forced) should skip all files.
        """
        syncer = e2e_env["syncer"]
        manifest = e2e_env["manifest"]
        source_dir = e2e_env["source_dir"]
        expected_files = e2e_env["expected_files"]

        source = {"label": "TestSource", "path": str(source_dir)}

        # ── First run: full backup ────────────────────────────────────────
        changed_1, _ = syncer.scan_source(source, force_full=True)
        assert len(changed_1) == len(expected_files)

        run_id_1 = manifest.create_run(full_backup=True)
        for fm in changed_1:
            bp = syncer.copy_file(fm, run_id_1)
            manifest.record_file(run_id_1, fm, bp, key_fingerprint=syncer.key_fingerprint)
        manifest.flush()
        manifest.finalize_run(run_id_1, {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "files_transferred": len(changed_1),
            "files_skipped": 0,
            "files_failed": 0,
            "bytes_transferred": sum(f["size"] for f in changed_1),
        })

        # ── Second run: incremental (no force_full) ──────────────────────
        changed_2, skipped_2 = syncer.scan_source(source, force_full=False)

        assert len(changed_2) == 0, (
            f"Expected 0 changed files on second scan, got {len(changed_2)}: "
            f"{[f['name'] for f in changed_2]}"
        )
        # All non-excluded files should be skipped (cached), plus the excluded file
        assert skipped_2 >= len(expected_files), (
            f"Expected at least {len(expected_files)} skipped, got {skipped_2}"
        )

    def test_e2e_key_fingerprint_tracked(self, e2e_env):
        """
        Verify that key_fingerprint is populated in file records after backup.
        """
        syncer = e2e_env["syncer"]
        manifest = e2e_env["manifest"]
        source_dir = e2e_env["source_dir"]
        expected_files = e2e_env["expected_files"]

        source = {"label": "TestSource", "path": str(source_dir)}

        # The syncer should have a key fingerprint (16 hex chars)
        fp = syncer.key_fingerprint
        assert fp is not None, "key_fingerprint should not be None when encryption is enabled"
        assert len(fp) == 16, f"Expected 16-char fingerprint, got {len(fp)}: {fp}"
        assert all(c in "0123456789abcdef" for c in fp), (
            f"Fingerprint should be hex, got: {fp}"
        )

        # Run backup
        changed, _ = syncer.scan_source(source, force_full=True)
        run_id = manifest.create_run(full_backup=True)
        for fm in changed:
            bp = syncer.copy_file(fm, run_id)
            manifest.record_file(run_id, fm, bp, key_fingerprint=syncer.key_fingerprint)
        manifest.flush()
        manifest.finalize_run(run_id, {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "files_transferred": len(changed),
            "files_skipped": 0,
            "files_failed": 0,
            "bytes_transferred": sum(f["size"] for f in changed),
        })

        # Every file record should have key_fingerprint set
        file_records = manifest.get_files(run_id)
        assert len(file_records) == len(expected_files)

        for rec in file_records:
            assert rec["key_fingerprint"] == fp, (
                f"File {rec['name']} has fingerprint {rec['key_fingerprint']!r}, expected {fp!r}"
            )
