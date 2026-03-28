"""
tests/test_syncer_copy.py — Unit tests for LocalSyncer.copy_file

Run with:  pytest backend/tests/test_syncer_copy.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from syncer import LocalSyncer, _hash_file


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_config(
    ssd_path="/tmp/fake_ssd",
    encryption_key=None,
    verify_checksums=True,
    secondary_ssd_path="",
):
    cfg = MagicMock()
    cfg.ssd_path              = ssd_path
    cfg.secondary_ssd_path    = secondary_ssd_path
    cfg.encryption_key        = encryption_key
    cfg.hkdf_salt             = b"ghostbackup-stream-v1"
    cfg.encryption_config_enabled = bool(encryption_key)
    cfg.encryption_enabled    = bool(encryption_key)
    cfg.chunk_size_bytes      = 65536
    cfg.verify_checksums      = verify_checksums
    cfg.exclude_patterns      = []
    cfg.max_file_size_bytes   = 5 * 1024 ** 3
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


def _file_meta(source_dir: Path, name: str, label: str = "Test") -> dict:
    """Build a file_meta dict matching what scan_source produces."""
    src = source_dir / name
    stat = src.stat()
    return {
        "source_label":  label,
        "name":          src.name,
        "original_path": str(src),
        "rel_path":      name,
        "size":          stat.st_size,
        "mtime":         stat.st_mtime,
        "xxhash":        _hash_file(src),
    }


# ── Tests ────────────────────────────────────────────────────────────────────

class TestCopyFileBasic:
    def test_copy_file_basic(self, tmp_path):
        """Copy a small file, verify destination exists and content matches."""
        source_dir = tmp_path / "source"
        dest_dir   = tmp_path / "ssd"
        source_dir.mkdir()
        dest_dir.mkdir()

        content = b"hello world backup"
        _write(source_dir, "doc.txt", content)
        meta = _file_meta(source_dir, "doc.txt")

        cfg  = _make_config(ssd_path=str(dest_dir), verify_checksums=False)
        mani = _make_manifest()
        s    = LocalSyncer(config=cfg, manifest=mani)

        result = s.copy_file(meta, run_id=1)
        dest   = Path(result)

        assert dest.exists()
        assert dest.read_bytes() == content

    def test_copy_file_atomic_write(self, tmp_path):
        """Verify .ghosttmp temp file is not left behind after copy."""
        source_dir = tmp_path / "source"
        dest_dir   = tmp_path / "ssd"
        source_dir.mkdir()
        dest_dir.mkdir()

        _write(source_dir, "file.bin", b"atomic test")
        meta = _file_meta(source_dir, "file.bin")

        cfg  = _make_config(ssd_path=str(dest_dir), verify_checksums=False)
        s    = LocalSyncer(config=cfg, manifest=_make_manifest())

        result = s.copy_file(meta, run_id=1)
        dest   = Path(result)

        # The final file should exist, but no .ghosttmp remnant
        assert dest.exists()
        tmp_files = list(dest.parent.glob("*.ghosttmp"))
        assert tmp_files == []

    def test_copy_file_checksum_verification(self, tmp_path):
        """Verify the returned backup matches source hash when checksums enabled."""
        source_dir = tmp_path / "source"
        dest_dir   = tmp_path / "ssd"
        source_dir.mkdir()
        dest_dir.mkdir()

        content = b"checksum test content " * 100
        _write(source_dir, "report.xlsx", content)
        meta = _file_meta(source_dir, "report.xlsx")

        cfg  = _make_config(ssd_path=str(dest_dir), verify_checksums=True)
        s    = LocalSyncer(config=cfg, manifest=_make_manifest())

        result = s.copy_file(meta, run_id=1)
        dest   = Path(result)

        # Destination hash must match source hash
        assert _hash_file(dest) == meta["xxhash"]

    def test_copy_file_creates_dirs(self, tmp_path):
        """Verify parent directories are created for nested rel_path."""
        source_dir = tmp_path / "source"
        dest_dir   = tmp_path / "ssd"
        source_dir.mkdir()
        dest_dir.mkdir()

        _write(source_dir, "deep/nested/dir/file.txt", b"nested")
        meta = _file_meta(source_dir, "deep/nested/dir/file.txt")

        cfg = _make_config(ssd_path=str(dest_dir), verify_checksums=False)
        s   = LocalSyncer(config=cfg, manifest=_make_manifest())

        result = s.copy_file(meta, run_id=1)
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"nested"


class TestCopyFileEncryption:
    def test_copy_file_with_encryption(self, tmp_path):
        """Copy with encryption key, verify encrypted output differs from source."""
        pytest.importorskip("cryptography")
        from cryptography.fernet import Fernet

        source_dir = tmp_path / "source"
        dest_dir   = tmp_path / "ssd"
        source_dir.mkdir()
        dest_dir.mkdir()

        content = b"sensitive accounting data " * 50
        _write(source_dir, "secret.xlsx", content)

        key  = Fernet.generate_key()
        meta = _file_meta(source_dir, "secret.xlsx")

        cfg  = _make_config(ssd_path=str(dest_dir), encryption_key=key, verify_checksums=True)
        s    = LocalSyncer(config=cfg, manifest=_make_manifest())

        result = s.copy_file(meta, run_id=1)
        dest   = Path(result)

        assert dest.exists()
        # Encrypted content must differ from plaintext
        assert dest.read_bytes() != content
        # File should start with GBENC1 magic header
        assert dest.read_bytes()[:6] == b"GBENC1"


class TestCopyFileSecondarySSD:
    def test_copy_file_secondary_ssd(self, tmp_path):
        """If secondary_ssd_path provided, verify file copied there too."""
        source_dir    = tmp_path / "source"
        primary_ssd   = tmp_path / "primary"
        secondary_ssd = tmp_path / "secondary"
        source_dir.mkdir()
        primary_ssd.mkdir()
        secondary_ssd.mkdir()

        _write(source_dir, "doc.txt", b"redundant data")
        meta = _file_meta(source_dir, "doc.txt")

        cfg = _make_config(
            ssd_path=str(primary_ssd),
            secondary_ssd_path=str(secondary_ssd),
            verify_checksums=False,
        )
        s = LocalSyncer(config=cfg, manifest=_make_manifest())

        s.copy_file(meta, run_id=1)

        # Check primary has the file
        primary_files = list(primary_ssd.rglob("doc.txt"))
        assert len(primary_files) == 1

        # Check secondary also has the file
        secondary_files = list(secondary_ssd.rglob("doc.txt"))
        assert len(secondary_files) == 1

        assert primary_files[0].read_bytes() == b"redundant data"
        assert secondary_files[0].read_bytes() == b"redundant data"
