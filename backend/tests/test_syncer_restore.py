"""
tests/test_syncer_restore.py — Unit tests for LocalSyncer.restore_files

Run with:  pytest backend/tests/test_syncer_restore.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from syncer import LocalSyncer, _hash_file


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_config(
    ssd_path="/tmp/fake_ssd",
    encryption_key=None,
    sources=None,
):
    cfg = MagicMock()
    cfg.ssd_path              = ssd_path
    cfg.secondary_ssd_path    = ""
    cfg.encryption_key        = encryption_key
    cfg.encryption_config_enabled = bool(encryption_key)
    cfg.encryption_enabled    = bool(encryption_key)
    cfg.chunk_size_bytes      = 65536
    cfg.verify_checksums      = False
    cfg.exclude_patterns      = []
    cfg.max_file_size_bytes   = 5 * 1024 ** 3
    cfg.get_enabled_sources.return_value = sources or []
    return cfg


def _make_manifest():
    m = MagicMock()
    m.get_file_hash.return_value = None
    return m


def _write(dir_: Path, name: str, content: bytes = b"data") -> Path:
    p = dir_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ── Tests ────────────────────────────────────────────────────────────────────

class TestRestoreBasic:
    def test_restore_basic(self, tmp_path):
        """Create a backed-up file, restore it, verify content."""
        backup_dir  = tmp_path / "backup"
        restore_dir = tmp_path / "restore"

        content = b"important document content"
        backup_file = _write(backup_dir, "Accounts/report.xlsx", content)

        cfg = _make_config(sources=[{"label": "Accounts", "path": "/data"}])
        s   = LocalSyncer(config=cfg, manifest=_make_manifest())

        files = [{
            "backup_path":   str(backup_file),
            "original_path": "/data/report.xlsx",
            "source_label":  "Accounts",
            "name":          "report.xlsx",
        }]

        result = s.restore_files(files, str(restore_dir))
        assert result["restored"] == 1
        assert result["failed"] == 0

        # Verify restored content matches
        restored_file = restore_dir / "report.xlsx"
        assert restored_file.exists()
        assert restored_file.read_bytes() == content

    def test_restore_creates_dest_dirs(self, tmp_path):
        """Verify destination directory structure is created on restore."""
        backup_dir  = tmp_path / "backup"
        restore_dir = tmp_path / "restore"

        backup_file = _write(backup_dir, "file.txt", b"nested restore")

        cfg = _make_config()
        s   = LocalSyncer(config=cfg, manifest=_make_manifest())

        files = [{
            "backup_path": str(backup_file),
            "name":        "deep/sub/file.txt",
        }]

        result = s.restore_files(files, str(restore_dir))
        assert result["restored"] == 1
        assert (restore_dir / "deep" / "sub" / "file.txt").exists()

    def test_restore_missing_backup_reports_failure(self, tmp_path):
        """Restoring a file whose backup doesn't exist reports failure."""
        restore_dir = tmp_path / "restore"

        cfg = _make_config()
        s   = LocalSyncer(config=cfg, manifest=_make_manifest())

        files = [{
            "backup_path": "/nonexistent/backup/file.xlsx",
            "name":        "file.xlsx",
        }]

        result = s.restore_files(files, str(restore_dir))
        assert result["failed"] == 1
        assert result["restored"] == 0
        assert any("not found" in e["error"] for e in result["errors"])


class TestRestoreEncryption:
    def test_restore_with_decryption(self, tmp_path):
        """Backup encrypted, restore, verify decrypted content matches original."""
        pytest.importorskip("cryptography")
        from cryptography.fernet import Fernet

        source_dir  = tmp_path / "source"
        ssd_dir     = tmp_path / "ssd"
        restore_dir = tmp_path / "restore"
        source_dir.mkdir()
        ssd_dir.mkdir()

        content = b"confidential payroll data " * 50
        src_file = _write(source_dir, "payroll.xlsx", content)

        key  = Fernet.generate_key()
        meta = {
            "source_label":  "HR",
            "name":          "payroll.xlsx",
            "original_path": str(src_file),
            "rel_path":      "payroll.xlsx",
            "size":          src_file.stat().st_size,
            "mtime":         src_file.stat().st_mtime,
            "xxhash":        _hash_file(src_file),
        }

        cfg = _make_config(
            ssd_path=str(ssd_dir),
            encryption_key=key,
            sources=[{"label": "HR", "path": str(source_dir)}],
        )
        cfg.verify_checksums = True
        mani = _make_manifest()
        s    = LocalSyncer(config=cfg, manifest=mani)

        # Copy (encrypts)
        backup_path = s.copy_file(meta, run_id=1)

        # Restore (decrypts)
        files = [{
            "backup_path":   backup_path,
            "original_path": str(src_file),
            "source_label":  "HR",
            "name":          "payroll.xlsx",
        }]
        result = s.restore_files(files, str(restore_dir))
        assert result["restored"] == 1

        restored = restore_dir / "payroll.xlsx"
        assert restored.read_bytes() == content


class TestRestorePathTraversal:
    def test_restore_path_traversal_blocked(self, tmp_path):
        """Attempt restore with '..' in name, verify it's blocked."""
        backup_dir  = tmp_path / "backup"
        restore_dir = tmp_path / "restore"

        backup_file = _write(backup_dir, "legit.txt", b"data")

        cfg = _make_config()
        s   = LocalSyncer(config=cfg, manifest=_make_manifest())

        files = [{
            "backup_path": str(backup_file),
            "name":        "../../etc/passwd",
        }]

        result = s.restore_files(files, str(restore_dir))
        assert result["failed"] == 1
        assert any("traversal" in e["error"].lower() for e in result["errors"])
