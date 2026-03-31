"""
tests/test_syncer_verify.py — Unit tests for LocalSyncer.verify_backups

Run with:  pytest backend/tests/test_syncer_verify.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from syncer import LocalSyncer, _hash_file


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_config(ssd_path="/tmp/fake_ssd", sources=None):
    cfg = MagicMock()
    cfg.ssd_path              = ssd_path
    cfg.secondary_ssd_path    = ""
    cfg.encryption_key        = None
    cfg.hkdf_salt             = b"ghostbackup-stream-v1"
    cfg.encryption_config_enabled = False
    cfg.encryption_enabled    = False
    cfg.chunk_size_bytes      = 65536
    cfg.verify_checksums      = True
    cfg.exclude_patterns      = []
    cfg.max_file_size_bytes   = 5 * 1024 ** 3
    cfg.get_enabled_sources.return_value = sources or []
    return cfg


def _make_manifest():
    m = MagicMock()
    m.get_file_hash.return_value = None
    m.get_latest_backed_up_files_for_source.return_value = []
    return m


def _write(dir_: Path, name: str, content: bytes = b"data") -> Path:
    p = dir_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ── Tests ────────────────────────────────────────────────────────────────────

class TestVerifyBackups:
    def test_verify_intact_file(self, tmp_path):
        """Create a file, record its hash, verify returns OK."""
        backup_dir = tmp_path / "ssd" / "Accounts"
        backup_dir.mkdir(parents=True)

        content     = b"intact file contents"
        backup_file = _write(backup_dir, "report.xlsx", content)
        file_hash   = _hash_file(backup_file)

        mani = _make_manifest()
        mani.get_latest_backed_up_files_for_source.return_value = [{
            "backup_path": str(backup_file),
            "xxhash":      file_hash,
            "name":        "report.xlsx",
        }]

        cfg = _make_config(sources=[{"label": "Accounts", "name": "Accounts"}])
        s   = LocalSyncer(config=cfg, manifest=mani)

        result = s.verify_backups()
        assert result["verified"] == 1
        assert result["failed"]   == 0
        assert result["missing"]  == 0

    def test_verify_corrupted_file(self, tmp_path):
        """Create a file, modify it, verify catches the corruption."""
        backup_dir = tmp_path / "ssd" / "Accounts"
        backup_dir.mkdir(parents=True)

        backup_file   = _write(backup_dir, "report.xlsx", b"original content")
        original_hash = _hash_file(backup_file)

        # Corrupt the file
        backup_file.write_bytes(b"corrupted content!!!")

        mani = _make_manifest()
        mani.get_latest_backed_up_files_for_source.return_value = [{
            "backup_path": str(backup_file),
            "xxhash":      original_hash,
            "name":        "report.xlsx",
        }]

        cfg = _make_config(sources=[{"label": "Accounts", "name": "Accounts"}])
        s   = LocalSyncer(config=cfg, manifest=mani)

        result = s.verify_backups()
        assert result["verified"] == 0
        assert result["failed"]   == 1
        assert any("mismatch" in e["error"].lower() for e in result["errors"])

    def test_verify_missing_file(self, tmp_path):
        """Record a file that doesn't exist, verify reports missing."""
        mani = _make_manifest()
        mani.get_latest_backed_up_files_for_source.return_value = [{
            "backup_path": "/nonexistent/ssd/Accounts/gone.xlsx",
            "xxhash":      "abc123",
            "name":        "gone.xlsx",
        }]

        cfg = _make_config(sources=[{"label": "Accounts", "name": "Accounts"}])
        s   = LocalSyncer(config=cfg, manifest=mani)

        result = s.verify_backups()
        assert result["verified"] == 0
        assert result["missing"]  == 1
        assert any("missing" in e["error"].lower() for e in result["errors"])


class TestVerifyFiles:
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
