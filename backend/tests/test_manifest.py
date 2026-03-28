"""
tests/test_manifest.py — Unit tests for ManifestDB

Run with:  pytest backend/tests/test_manifest.py -v
"""

import pytest

from manifest import ManifestDB
from utils import fmt_bytes as _fmt_bytes, fmt_duration as _fmt_duration


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Fresh in-memory-backed ManifestDB for each test."""
    return ManifestDB(db_path=tmp_path / "test.db")


# ── Run lifecycle ─────────────────────────────────────────────────────────────

def test_create_run_returns_id(db):
    run_id = db.create_run(full_backup=False)
    assert run_id == 1


def test_create_multiple_runs_increments_id(db):
    id1 = db.create_run()
    id2 = db.create_run()
    assert id2 == id1 + 1


def test_finalize_run_updates_status(db):
    run_id = db.create_run()
    db.finalize_run(run_id, {
        "started_at":        "2026-01-01T08:00:00",
        "finished_at":       "2026-01-01T08:05:00",
        "status":            "success",
        "files_transferred": 10,
        "files_skipped":     2,
        "files_failed":      0,
        "bytes_transferred": 1024 * 1024,
        "errors":            [],
    })
    run = db.get_run(run_id)
    assert run["status"] == "success"
    assert run["files_transferred"] == 10
    assert run["duration_seconds"] == 300


def test_finalize_run_failed_status(db):
    run_id = db.create_run()
    db.finalize_run(run_id, {
        "started_at": "2026-01-01T08:00:00",
        "finished_at": "2026-01-01T08:01:00",
        "status": "failed",
        "files_transferred": 0,
        "files_skipped": 0,
        "files_failed": 5,
        "bytes_transferred": 0,
        "errors": [{"file": "x.xlsx", "error": "locked"}],
    })
    run = db.get_run(run_id)
    assert run["status"] == "failed"
    assert run["files_failed"] == 5


def test_get_run_not_found_returns_none(db):
    assert db.get_run(9999) is None


def test_get_runs_returns_list(db):
    db.create_run()
    db.create_run()
    runs = db.get_runs(limit=10)
    assert len(runs) == 2


def test_get_latest_successful_run(db):
    r1 = db.create_run()
    db.finalize_run(r1, {
        "started_at": "2026-01-01T08:00:00", "finished_at": "2026-01-01T08:01:00",
        "status": "success", "files_transferred": 5, "files_skipped": 0,
        "files_failed": 0, "bytes_transferred": 512, "errors": [],
    })
    result = db.get_latest_successful_run()
    assert result is not None
    assert result["id"] == r1


# ── File records ──────────────────────────────────────────────────────────────

def test_record_and_retrieve_file(db):
    run_id = db.create_run()
    db.record_file(run_id, {
        "source_label":  "Accounts",
        "name":          "invoice.xlsx",
        "original_path": "/data/invoice.xlsx",
        "size":          2048,
        "mtime":         1_700_000_000.0,
        "xxhash":        "abc123",
    }, "/backup/Accounts/invoice.xlsx")

    files = db.get_files(run_id)
    assert len(files) == 1
    assert files[0]["name"] == "invoice.xlsx"
    assert files[0]["source_label"] == "Accounts"


def test_record_file_stores_key_fingerprint(db):
    run_id = db.create_run()
    db.record_file(run_id, {
        "source_label":  "Accounts",
        "name":          "contract.pdf",
        "original_path": "/data/contract.pdf",
        "size":          512,
        "mtime":         1_700_000_000.0,
        "xxhash":        "def456",
    }, "/backup/Accounts/contract.pdf", key_fingerprint="abcd1234efgh5678")

    row = db._conn.execute(
        "SELECT key_fingerprint FROM files WHERE name = 'contract.pdf'"
    ).fetchone()
    assert row is not None
    assert row[0] == "abcd1234efgh5678"


def test_get_files_filtered_by_library(db):
    run_id = db.create_run()
    db.record_file(run_id, {
        "source_label": "Accounts", "name": "a.xlsx",
        "original_path": "/data/a.xlsx", "size": 100,
        "mtime": 0.0, "xxhash": "h1",
    }, "/backup/Accounts/a.xlsx")
    db.record_file(run_id, {
        "source_label": "HR", "name": "b.xlsx",
        "original_path": "/data/b.xlsx", "size": 100,
        "mtime": 0.0, "xxhash": "h2",
    }, "/backup/HR/b.xlsx")

    accounts_files = db.get_files(run_id, library="Accounts")
    assert len(accounts_files) == 1
    assert accounts_files[0]["name"] == "a.xlsx"


def test_get_latest_backed_up_files_for_source(db):
    run_id = db.create_run()
    db.record_file(run_id, {
        "source_label": "Accounts", "name": "report.xlsx",
        "original_path": "/data/report.xlsx", "size": 200,
        "mtime": 0.0, "xxhash": "hashxyz",
    }, "/backup/Accounts/report.xlsx")
    db.finalize_run(run_id, {
        "started_at": "2026-01-01T08:00:00", "finished_at": "2026-01-01T08:01:00",
        "status": "success", "files_transferred": 1, "files_skipped": 0,
        "files_failed": 0, "bytes_transferred": 200, "errors": [],
    })

    rows = db.get_latest_backed_up_files_for_source("Accounts")
    assert len(rows) == 1
    assert rows[0]["name"] == "report.xlsx"
    assert rows[0]["xxhash"] == "hashxyz"


# ── Hash cache ────────────────────────────────────────────────────────────────

def test_get_file_hash_missing_returns_none(db):
    assert db.get_file_hash("/data/nonexistent.xlsx") is None


def test_save_and_retrieve_file_hash(db):
    db.save_file_hash("/data/file.xlsx", "hash1", 1_700_000_000.0, 1024)
    cached = db.get_file_hash("/data/file.xlsx")
    assert cached is not None
    assert cached["xxhash"] == "hash1"
    assert cached["size"] == 1024


def test_save_file_hash_overwrites_on_conflict(db):
    db.save_file_hash("/data/file.xlsx", "old_hash", 0.0, 100)
    db.save_file_hash("/data/file.xlsx", "new_hash", 1.0, 200)
    cached = db.get_file_hash("/data/file.xlsx")
    assert cached["xxhash"] == "new_hash"


def test_clear_file_hashes_by_prefix(db):
    db.save_file_hash("/data/accounts/file1.xlsx", "h1", 0.0, 100)
    db.save_file_hash("/data/accounts/file2.xlsx", "h2", 0.0, 100)
    db.save_file_hash("/data/other/file3.xlsx",    "h3", 0.0, 100)

    removed = db.clear_file_hashes("/data/accounts")
    assert removed == 2
    assert db.get_file_hash("/data/other/file3.xlsx") is not None
    assert db.get_file_hash("/data/accounts/file1.xlsx") is None


def test_clear_all_file_hashes(db):
    db.save_file_hash("/data/a.xlsx", "h1", 0.0, 10)
    db.save_file_hash("/data/b.xlsx", "h2", 0.0, 10)
    removed = db.clear_file_hashes()
    assert removed == 2


# ── Pruning ───────────────────────────────────────────────────────────────────

def test_get_backup_files_for_prune_excludes_recent(db):
    run_id = db.create_run()
    db.record_file(run_id, {
        "source_label": "Accounts", "name": "old.xlsx",
        "original_path": "/data/old.xlsx", "size": 50,
        "mtime": 0.0, "xxhash": "hh",
    }, "/backup/Accounts/old.xlsx")
    db.finalize_run(run_id, {
        "started_at": "2020-01-01T08:00:00", "finished_at": "2020-01-01T08:01:00",
        "status": "success", "files_transferred": 1, "files_skipped": 0,
        "files_failed": 0, "bytes_transferred": 50, "errors": [],
    })

    # Cutoff in the future — should include the run
    rows = db.get_backup_files_for_prune("Accounts", "2030-01-01T00:00:00")
    assert len(rows) == 1

    # Cutoff before the run — should not include it
    rows = db.get_backup_files_for_prune("Accounts", "2019-01-01T00:00:00")
    assert len(rows) == 0


def test_mark_run_pruned(db):
    run_id = db.create_run()
    db.finalize_run(run_id, {
        "started_at": "2026-03-01T08:00:00", "finished_at": "2026-03-01T08:01:00",
        "status": "success", "files_transferred": 0, "files_skipped": 0,
        "files_failed": 0, "bytes_transferred": 0, "errors": [],
    })
    db.mark_run_pruned("2026-03-01", "2026-03-02")
    run = db.get_run(run_id)
    assert run["pruned"] == 1


# ── Config audit ──────────────────────────────────────────────────────────────

def test_log_and_retrieve_config_change(db):
    db.log_config_change("ssd_path", "/old/path", "/new/path")
    audit = db.get_config_audit()
    assert len(audit) == 1
    assert audit[0]["field"] == "ssd_path"


def test_config_audit_ordered_most_recent_first(db):
    db.log_config_change("field_a", None, "value_1")
    db.log_config_change("field_b", None, "value_2")
    audit = db.get_config_audit()
    assert audit[0]["field"] == "field_b"


# ── Logging ───────────────────────────────────────────────────────────────────

def test_log_and_retrieve_all_levels(db):
    run_id = db.create_run()
    db.log(run_id, "INFO",    "Scan started")
    db.log(run_id, "WARNING", "File skipped")
    db.log(run_id, "ERROR",   "File failed")

    all_logs = db.get_logs(run_id)
    assert len(all_logs) == 3


def test_get_logs_filtered_by_level(db):
    run_id = db.create_run()
    db.log(run_id, "INFO",  "ok")
    db.log(run_id, "ERROR", "bad")

    error_logs = db.get_logs(run_id, level="ERROR")
    assert len(error_logs) == 1
    assert error_logs[0]["level"] == "ERROR"


# ── Utilities ─────────────────────────────────────────────────────────────────

# ── Flush ────────────────────────────────────────────────────────────────────

def test_flush_commits_pending(tmp_path):
    """Call record_file() multiple times, call flush(), verify data is persisted."""
    db_path = tmp_path / "flush_test.db"
    db = ManifestDB(db_path=db_path)

    run_id = db.create_run()

    # record_file does NOT auto-commit — data is pending
    db.record_file(run_id, {
        "source_label": "Accounts", "name": "a.xlsx",
        "original_path": "/data/a.xlsx", "size": 100,
        "mtime": 1_700_000_000.0, "xxhash": "h1",
    }, "/backup/Accounts/a.xlsx")

    db.record_file(run_id, {
        "source_label": "Accounts", "name": "b.xlsx",
        "original_path": "/data/b.xlsx", "size": 200,
        "mtime": 1_700_000_001.0, "xxhash": "h2",
    }, "/backup/Accounts/b.xlsx")

    # Flush to commit pending writes
    db.flush()
    db.close()

    # Reopen from disk and verify all records were persisted
    db2 = ManifestDB(db_path=db_path)
    files = db2.get_files(run_id)
    assert len(files) == 2
    names = {f["name"] for f in files}
    assert names == {"a.xlsx", "b.xlsx"}
    db2.close()


@pytest.mark.parametrize("b, expected_unit", [
    (0,             "B"),
    (512,           "B"),
    (2048,          "KB"),
    (2 * 1024**2,   "MB"),
    (2 * 1024**3,   "GB"),
])
def test_fmt_bytes(b, expected_unit):
    assert expected_unit in _fmt_bytes(b)


@pytest.mark.parametrize("seconds, expected", [
    (0,    "—"),
    (30,   "30s"),
    (90,   "1m 30s"),
    (3661, "1h 1m 1s"),
])
def test_fmt_duration(seconds, expected):
    assert _fmt_duration(seconds) == expected


# ── Schema migration ──────────────────────────────────────────────────────────

def test_schema_version_is_set_on_fresh_db(tmp_path):
    db = ManifestDB(tmp_path / "test.db")
    row = db._conn.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row[0] == ManifestDB._SCHEMA_VERSION


def test_schema_migration_idempotent(tmp_path):
    """Creating ManifestDB twice on the same file must not raise."""
    ManifestDB(tmp_path / "test.db")
    ManifestDB(tmp_path / "test.db")  # should not raise or duplicate version rows


def test_db_path_property(tmp_path):
    db = ManifestDB(tmp_path / "test.db")
    assert db.db_path == tmp_path / "test.db"
