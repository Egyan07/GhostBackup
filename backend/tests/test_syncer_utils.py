"""
tests/test_syncer_utils.py — Unit tests for syncer utility functions

Run with:  pytest backend/tests/test_syncer_utils.py -v
"""

import pytest

from syncer import _should_exclude, _sanitise_label, _hash_bytes, get_ssd_status


# ── _should_exclude ───────────────────────────────────────────────────────────

def test_exclude_by_exact_filename():
    assert _should_exclude("thumbs.db", ["thumbs.db"])


def test_no_exclude_when_no_patterns():
    assert not _should_exclude("invoice.xlsx", [])


def test_no_exclude_non_matching_pattern():
    assert not _should_exclude("invoice.xlsx", ["thumbs.db", "*.tmp"])


def test_exclude_by_glob_extension():
    assert _should_exclude("temp_file.tmp", ["*.tmp"])
    assert _should_exclude("backup.bak", ["*.bak"])


def test_exclude_folder_name_in_path():
    assert _should_exclude("node_modules/lodash/index.js", ["node_modules"])


def test_exclude_nested_temp_folder():
    assert _should_exclude(".git/config", [".git"])


def test_no_exclude_similar_but_different_name():
    assert not _should_exclude("node_module/file.js", ["node_modules"])


def test_exclude_by_full_path_glob():
    assert _should_exclude("cache/data/big.dat", ["cache/*"])


# ── _sanitise_label ───────────────────────────────────────────────────────────

def test_sanitise_label_clean_alphanumeric():
    assert _sanitise_label("Accounts2024") == "Accounts2024"


def test_sanitise_label_preserves_spaces_hyphens_underscores():
    result = _sanitise_label("HR Payroll-Data_2024")
    assert result == "HR Payroll-Data_2024"


def test_sanitise_label_replaces_special_chars():
    result = _sanitise_label("HR/Payroll:Data")
    assert "/" not in result
    assert ":" not in result
    assert len(result) > 0


def test_sanitise_label_empty_string_returns_source():
    assert _sanitise_label("") == "source"


def test_sanitise_label_all_special_chars_returns_source():
    assert _sanitise_label("!!!@@@###") == "source"


def test_sanitise_label_strips_leading_trailing_whitespace():
    result = _sanitise_label("  Accounts  ")
    assert result == "Accounts"


# ── _hash_bytes ───────────────────────────────────────────────────────────────

def test_hash_bytes_is_deterministic():
    assert _hash_bytes(b"hello world") == _hash_bytes(b"hello world")


def test_hash_bytes_differs_for_different_input():
    assert _hash_bytes(b"hello") != _hash_bytes(b"world")


def test_hash_bytes_empty_input():
    result = _hash_bytes(b"")
    assert isinstance(result, str)
    assert len(result) > 0


def test_hash_bytes_returns_hex_string():
    result = _hash_bytes(b"test data")
    assert all(c in "0123456789abcdef" for c in result)


# ── get_ssd_status ────────────────────────────────────────────────────────────

def test_get_ssd_status_empty_path():
    result = get_ssd_status("")
    assert result["status"] == "not_configured"
    assert "error" in result


def test_get_ssd_status_none_path():
    result = get_ssd_status(None)
    assert result["status"] == "not_configured"


def test_get_ssd_status_nonexistent_path():
    result = get_ssd_status("/nonexistent/path/xyz_ghostbackup_test")
    assert result["status"] == "disconnected"
    assert "error" in result


def test_get_ssd_status_valid_path(tmp_path):
    result = get_ssd_status(str(tmp_path))
    assert result["status"] == "ok"
    assert "available_gb" in result
    assert "total_gb" in result
    assert result["total_gb"] > 0


# =============================================================================
#   Regression — fix #4: prune marks runs correctly
# =============================================================================

def test_prune_calls_mark_run_pruned_when_files_deleted(tmp_path):
    """
    Regression: prune_old_backups must call manifest.mark_run_pruned
    for dates where files were actually deleted.
    """
    from unittest.mock import MagicMock, patch
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    from syncer import LocalSyncer

    # Create a real file to be pruned
    backup_file = tmp_path / "old_backup.xlsx"
    backup_file.write_bytes(b"data")

    old_date = (datetime.now(timezone.utc) - timedelta(days=400))
    old_ts   = old_date.isoformat()

    cfg = MagicMock()
    cfg.get_enabled_sources.return_value = [{"label": "Accounts"}]
    cfg.secondary_ssd_path = ""
    cfg.encryption_key     = None
    cfg.encryption_enabled = False

    manifest = MagicMock()
    manifest.get_backup_files_for_prune.return_value = [{
        "backup_path": str(backup_file),
        "started_at":  old_ts,
    }]

    syncer = LocalSyncer(config=cfg, manifest=manifest)
    removed = syncer.prune_old_backups(daily_days=365, weekly_days=2555, guard_days=7)

    assert removed == 1
    assert not backup_file.exists()
    # mark_run_pruned must have been called at least once
    manifest.mark_run_pruned.assert_called_once()


def test_prune_does_not_mark_pruned_when_nothing_deleted(tmp_path):
    """
    Regression: mark_run_pruned must NOT be called if no files were deleted.
    """
    from unittest.mock import MagicMock
    from datetime import datetime, timezone, timedelta
    from syncer import LocalSyncer

    cfg = MagicMock()
    cfg.get_enabled_sources.return_value = [{"label": "Accounts"}]
    cfg.secondary_ssd_path = ""
    cfg.encryption_key     = None
    cfg.encryption_enabled = False

    manifest = MagicMock()
    # Return a file that doesn't exist on disk — nothing deleted
    manifest.get_backup_files_for_prune.return_value = [{
        "backup_path": str(tmp_path / "nonexistent.xlsx"),
        "started_at":  (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
    }]

    syncer = LocalSyncer(config=cfg, manifest=manifest)
    removed = syncer.prune_old_backups(daily_days=365, weekly_days=2555, guard_days=7)

    assert removed == 0
    manifest.mark_run_pruned.assert_not_called()
