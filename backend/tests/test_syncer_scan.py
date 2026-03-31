"""
tests/test_syncer_scan.py — Unit tests for LocalSyncer.scan_source

Run with:  pytest backend/tests/test_syncer_scan.py -v
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from syncer import LocalSyncer


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_config(
    exclude_patterns=None,
    max_file_size_gb=5,
    concurrency=4,
):
    cfg = MagicMock()
    cfg.exclude_patterns    = exclude_patterns or []
    cfg.max_file_size_bytes = max_file_size_gb * 1024 ** 3
    cfg.chunk_size_bytes    = 65536
    cfg.ssd_path            = "/tmp/fake_ssd"
    cfg.encryption_key            = None
    cfg.hkdf_salt                 = b"ghostbackup-stream-v1"
    cfg.encryption_enabled        = False
    cfg.encryption_config_enabled = False
    return cfg


def _make_manifest():
    m = MagicMock()
    # By default no cached hashes — everything appears changed
    m.get_file_hash.return_value = None
    return m


@pytest.fixture
def source_dir(tmp_path):
    """A real temporary directory used as the backup source."""
    return tmp_path


@pytest.fixture
def syncer():
    cfg = _make_config()
    mani = _make_manifest()
    return LocalSyncer(config=cfg, manifest=mani)


def _write(dir_: Path, name: str, content: bytes = b"data") -> Path:
    p = dir_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ── Basic scanning ────────────────────────────────────────────────────────────

class TestScanSourceBasic:
    def test_empty_source_returns_zero_changed(self, syncer, source_dir):
        changed, skipped = syncer.scan_source({"label": "Test", "path": str(source_dir)})
        assert changed == []
        assert skipped == 0

    def test_single_file_detected_as_changed(self, syncer, source_dir):
        _write(source_dir, "invoice.xlsx")
        changed, _ = syncer.scan_source({"label": "Test", "path": str(source_dir)})
        assert len(changed) == 1
        assert changed[0]["name"] == "invoice.xlsx"

    def test_multiple_files_all_detected(self, syncer, source_dir):
        _write(source_dir, "a.xlsx")
        _write(source_dir, "b.xlsx")
        _write(source_dir, "c.docx")
        changed, _ = syncer.scan_source({"label": "Test", "path": str(source_dir)})
        assert len(changed) == 3

    def test_nested_files_detected(self, syncer, source_dir):
        _write(source_dir, "sub/folder/report.xlsx")
        changed, _ = syncer.scan_source({"label": "Test", "path": str(source_dir)})
        assert len(changed) == 1
        assert changed[0]["name"] == "report.xlsx"

    def test_directories_not_counted_as_files(self, syncer, source_dir):
        (source_dir / "empty_dir").mkdir()
        changed, skipped = syncer.scan_source({"label": "Test", "path": str(source_dir)})
        assert changed == []
        assert skipped == 0

    def test_file_meta_contains_required_keys(self, syncer, source_dir):
        _write(source_dir, "report.xlsx", b"content")
        changed, _ = syncer.scan_source({"label": "Accounts", "path": str(source_dir)})
        meta = changed[0]
        for key in ("source_label", "name", "original_path", "rel_path", "size", "mtime", "xxhash"):
            assert key in meta, f"missing key: {key}"

    def test_source_label_propagated_to_file_meta(self, syncer, source_dir):
        _write(source_dir, "file.xlsx")
        changed, _ = syncer.scan_source({"label": "HR Payroll", "path": str(source_dir)})
        assert changed[0]["source_label"] == "HR Payroll"

    def test_file_size_recorded_correctly(self, syncer, source_dir):
        content = b"A" * 1234
        _write(source_dir, "sized.bin", content)
        changed, _ = syncer.scan_source({"label": "T", "path": str(source_dir)})
        assert changed[0]["size"] == 1234

    def test_source_not_found_raises(self, syncer):
        with pytest.raises(FileNotFoundError):
            syncer.scan_source({"label": "T", "path": "/nonexistent/path/xyz"})


# ── Exclusion patterns ────────────────────────────────────────────────────────

class TestScanSourceExclusions:
    def test_excluded_file_counted_as_skipped(self, source_dir):
        cfg = _make_config(exclude_patterns=["*.tmp"])
        s = LocalSyncer(config=cfg, manifest=_make_manifest())
        _write(source_dir, "tempfile.tmp")
        changed, skipped = s.scan_source({"label": "T", "path": str(source_dir)})
        assert changed == []
        assert skipped == 1

    def test_non_excluded_file_not_skipped(self, source_dir):
        cfg = _make_config(exclude_patterns=["*.tmp"])
        s = LocalSyncer(config=cfg, manifest=_make_manifest())
        _write(source_dir, "real.xlsx")
        changed, skipped = s.scan_source({"label": "T", "path": str(source_dir)})
        assert len(changed) == 1
        assert skipped == 0

    def test_excluded_folder_skips_all_children(self, source_dir):
        cfg = _make_config(exclude_patterns=["node_modules"])
        s = LocalSyncer(config=cfg, manifest=_make_manifest())
        _write(source_dir, "node_modules/lodash/index.js")
        _write(source_dir, "node_modules/react/index.js")
        _write(source_dir, "src/main.js")
        changed, skipped = s.scan_source({"label": "T", "path": str(source_dir)})
        assert len(changed) == 1
        assert skipped == 2

    def test_multiple_patterns_all_applied(self, source_dir):
        cfg = _make_config(exclude_patterns=["*.tmp", "Thumbs.db", ".git"])
        s = LocalSyncer(config=cfg, manifest=_make_manifest())
        _write(source_dir, "file.tmp")
        _write(source_dir, "Thumbs.db")
        _write(source_dir, ".git/config")
        _write(source_dir, "real.xlsx")
        changed, skipped = s.scan_source({"label": "T", "path": str(source_dir)})
        assert len(changed) == 1
        assert changed[0]["name"] == "real.xlsx"
        assert skipped == 3


# ── Incremental detection (hash cache) ───────────────────────────────────────

class TestScanSourceIncremental:
    def test_unchanged_file_skipped_when_hash_matches(self, source_dir):
        cfg  = _make_config()
        mani = _make_manifest()
        s    = LocalSyncer(config=cfg, manifest=mani)
        f    = _write(source_dir, "stable.xlsx", b"stable content")
        stat = f.stat()

        from syncer import _hash_file
        file_hash = _hash_file(f, cfg.chunk_size_bytes)
        mani.get_file_hash.return_value = {
            "xxhash": file_hash,
            "mtime":  stat.st_mtime,
            "size":   stat.st_size,
        }

        changed, skipped = s.scan_source({"label": "T", "path": str(source_dir)})
        assert changed == []
        assert skipped == 1

    def test_changed_file_detected_when_hash_differs(self, source_dir):
        cfg  = _make_config()
        mani = _make_manifest()
        s    = LocalSyncer(config=cfg, manifest=mani)
        f    = _write(source_dir, "changed.xlsx", b"new content")
        stat = f.stat()

        # Cache reports an old hash
        mani.get_file_hash.return_value = {
            "xxhash": "old_hash_value",
            "mtime":  stat.st_mtime,
            "size":   stat.st_size,
        }

        changed, _ = s.scan_source({"label": "T", "path": str(source_dir)})
        assert len(changed) == 1

    def test_force_full_ignores_hash_cache(self, source_dir):
        cfg  = _make_config()
        mani = _make_manifest()
        s    = LocalSyncer(config=cfg, manifest=mani)
        f    = _write(source_dir, "file.xlsx", b"data")
        stat = f.stat()

        from syncer import _hash_file
        file_hash = _hash_file(f, cfg.chunk_size_bytes)
        # Even though cache matches exactly, force_full should include the file
        mani.get_file_hash.return_value = {
            "xxhash": file_hash,
            "mtime":  stat.st_mtime,
            "size":   stat.st_size,
        }

        changed, _ = s.scan_source({"label": "T", "path": str(source_dir)}, force_full=True)
        assert len(changed) == 1


# ── Max file size guard ───────────────────────────────────────────────────────

class TestScanSourceSizeLimit:
    def test_oversized_file_skipped(self, source_dir):
        # Set a tiny max (1 byte) to trigger the guard with any real file
        cfg = _make_config()
        cfg.max_file_size_bytes = 10  # 10 bytes limit
        s = LocalSyncer(config=cfg, manifest=_make_manifest())
        _write(source_dir, "big.bin", b"A" * 100)  # 100 bytes — over limit
        changed, skipped = s.scan_source({"label": "T", "path": str(source_dir)})
        assert changed == []
        assert skipped == 1

    def test_file_within_size_limit_included(self, source_dir):
        cfg = _make_config()
        cfg.max_file_size_bytes = 1000
        s = LocalSyncer(config=cfg, manifest=_make_manifest())
        _write(source_dir, "small.xlsx", b"A" * 100)
        changed, _ = s.scan_source({"label": "T", "path": str(source_dir)})
        assert len(changed) == 1
