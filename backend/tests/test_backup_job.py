"""
tests/test_backup_job.py — Integration tests for the core backup job execution path.

Tests the run_backup_job function end-to-end with mocked services, covering
the scan → copy → record → finalize pipeline (api.py lines 322–500).

Run with:  pytest backend/tests/test_backup_job.py -v
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api as api_module
from api import run_backup_job


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(source_path="/fake/source", extra_sources=None):
    cfg = MagicMock()
    sources = extra_sources or [{"label": "Accounts", "path": source_path, "enabled": True}]
    cfg.get_enabled_sources.return_value = sources
    cfg.concurrency               = 1
    cfg.circuit_breaker_threshold = 0.05
    return cfg


def _make_manifest(run_id=1):
    m = MagicMock()
    m.create_run.return_value = run_id
    m.finalize_run.return_value = None
    m.record_file.return_value = None
    m.log.return_value = None
    m.flush.return_value = None
    return m


def _make_syncer(changed_files=None, skipped=0):
    s = MagicMock()
    s.check_ssd.return_value = {"status": "ok"}
    s.scan_source.return_value = (changed_files or [], skipped)
    s.copy_file.return_value = "/fake/ssd/Accounts/file.xlsx"
    s.key_fingerprint = None
    return s


def _make_reporter():
    r = MagicMock()
    r.send_run_report = AsyncMock()
    r.alert_and_notify = AsyncMock()
    r.send_circuit_breaker_alert = AsyncMock()
    return r


def _make_scheduler():
    s = MagicMock()
    s.set_current_run_id.return_value = None
    s.reset_missed_alert.return_value = None
    return s


def _reset():
    api_module._active_run = None


def _run(coro):
    return asyncio.run(coro)


# Patch target for Path.exists inside api.py's run_backup_job source check
_PATH_EXISTS = "api.Path"


# ── Success path ──────────────────────────────────────────────────────────────

class TestRunBackupJobSuccess:
    def setup_method(self):
        _reset()

    def test_no_changed_files_completes_as_success(self, tmp_path):
        """Scan returns 0 files → run completes successfully."""
        src = tmp_path / "source"
        src.mkdir()
        cfg      = _make_cfg(source_path=str(src))
        manifest = _make_manifest(run_id=1)
        syncer   = _make_syncer(changed_files=[], skipped=3)
        reporter = _make_reporter()
        scheduler = _make_scheduler()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer, scheduler=scheduler,
            ))

        manifest.create_run.assert_called_once()
        manifest.finalize_run.assert_called_once()
        reporter.send_run_report.assert_awaited_once()
        run_state = manifest.finalize_run.call_args[0][1]
        assert run_state["status"] == "success"

    def test_changed_files_are_copied_and_recorded(self, tmp_path):
        """Files from scan are passed to copy_file and recorded in manifest."""
        src = tmp_path / "source"
        src.mkdir()
        changed = [{
            "name": "invoice.xlsx", "source_label": "Accounts",
            "original_path": str(src / "invoice.xlsx"),
            "rel_path": "invoice.xlsx", "size": 1024,
            "mtime": 1700000000.0, "xxhash": "abc123",
        }]
        cfg      = _make_cfg(source_path=str(src))
        manifest = _make_manifest(run_id=2)
        syncer   = _make_syncer(changed_files=changed)
        reporter = _make_reporter()
        scheduler = _make_scheduler()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer, scheduler=scheduler,
            ))

        syncer.copy_file.assert_called_once()
        manifest.record_file.assert_called_once()
        run_state = manifest.finalize_run.call_args[0][1]
        assert run_state["files_transferred"] == 1
        assert run_state["status"] == "success"

    def test_scheduler_reset_missed_alert_on_success(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        cfg       = _make_cfg(source_path=str(src))
        manifest  = _make_manifest()
        syncer    = _make_syncer()
        reporter  = _make_reporter()
        scheduler = _make_scheduler()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer, scheduler=scheduler,
            ))

        scheduler.reset_missed_alert.assert_called_once()

    def test_full_backup_flag_passed_to_create_run(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        cfg      = _make_cfg(source_path=str(src))
        manifest = _make_manifest()
        syncer   = _make_syncer()
        reporter = _make_reporter()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=True, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer,
            ))

        manifest.create_run.assert_called_once_with(full_backup=True)

    def test_skipped_files_count_tracked(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        cfg      = _make_cfg(source_path=str(src))
        manifest = _make_manifest()
        syncer   = _make_syncer(changed_files=[], skipped=7)
        reporter = _make_reporter()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer,
            ))

        run_state = manifest.finalize_run.call_args[0][1]
        assert run_state["files_skipped"] == 7


# ── Failure path ──────────────────────────────────────────────────────────────

class TestRunBackupJobFailures:
    def setup_method(self):
        _reset()

    def test_ssd_not_ready_aborts_without_creating_run(self):
        cfg      = _make_cfg()
        manifest = _make_manifest()
        syncer   = _make_syncer()
        syncer.check_ssd.return_value = {"status": "error", "error": "Drive not found"}
        reporter = _make_reporter()

        _run(run_backup_job(
            full=False, sources=None,
            cfg=cfg, manifest=manifest,
            reporter=reporter, syncer=syncer,
        ))

        manifest.create_run.assert_not_called()
        reporter.alert_and_notify.assert_awaited_once()

    def test_no_sources_configured_sends_fatal_alert(self, tmp_path):
        """Empty sources list raises RuntimeError → fatal alert is sent."""
        src = tmp_path / "source"
        src.mkdir()
        # Use a real source but filter it out via sources=["Nonexistent"]
        cfg      = _make_cfg(source_path=str(src))
        manifest = _make_manifest()
        syncer   = _make_syncer()
        reporter = _make_reporter()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=["Nonexistent"],
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer,
            ))

        reporter.alert_and_notify.assert_awaited_once()
        call_kwargs = reporter.alert_and_notify.call_args[1]
        assert call_kwargs["level"] == "critical"

    def test_file_copy_failure_increments_files_failed(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        changed = [{
            "name": "bad.xlsx", "source_label": "Accounts",
            "original_path": str(src / "bad.xlsx"),
            "rel_path": "bad.xlsx", "size": 512,
            "mtime": 1700000000.0, "xxhash": "xyz",
        }]
        cfg      = _make_cfg(source_path=str(src))
        manifest = _make_manifest()
        syncer   = _make_syncer(changed_files=changed)
        syncer.copy_file.side_effect = RuntimeError("disk full")
        reporter = _make_reporter()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer,
            ))

        run_state = manifest.finalize_run.call_args[0][1]
        assert run_state["files_failed"] >= 1

    def test_already_running_is_a_noop(self):
        api_module._active_run = {"status": "running"}
        cfg      = _make_cfg()
        manifest = _make_manifest()
        syncer   = _make_syncer()
        reporter = _make_reporter()

        _run(run_backup_job(
            full=False, sources=None,
            cfg=cfg, manifest=manifest,
            reporter=reporter, syncer=syncer,
        ))

        manifest.create_run.assert_not_called()

    def test_missing_source_folder_skips_library(self, tmp_path):
        """If the source path doesn't exist on disk, that library is skipped with an error."""
        cfg      = _make_cfg(source_path=str(tmp_path / "nonexistent"))
        manifest = _make_manifest()
        syncer   = _make_syncer()
        reporter = _make_reporter()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=None,
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer,
            ))

        run_state = manifest.finalize_run.call_args[0][1]
        assert len(run_state["errors"]) >= 1
        assert "not found" in run_state["errors"][0]["error"].lower()


# ── Source filtering ──────────────────────────────────────────────────────────

class TestRunBackupJobSourceFiltering:
    def setup_method(self):
        _reset()

    def test_sources_filter_limits_to_requested_labels(self, tmp_path):
        """sources=["Accounts"] means only Accounts is scanned, not HR."""
        src_a = tmp_path / "accounts"
        src_h = tmp_path / "hr"
        src_a.mkdir()
        src_h.mkdir()
        all_sources = [
            {"label": "Accounts", "path": str(src_a), "enabled": True},
            {"label": "HR",       "path": str(src_h), "enabled": True},
        ]
        cfg      = _make_cfg(extra_sources=all_sources)
        manifest = _make_manifest()
        syncer   = _make_syncer(changed_files=[])
        reporter = _make_reporter()

        with patch("api._backup_manifest_to_ssd", new=AsyncMock()), \
             patch("api._retry_locked_files", new=AsyncMock()):
            _run(run_backup_job(
                full=False, sources=["Accounts"],
                cfg=cfg, manifest=manifest,
                reporter=reporter, syncer=syncer,
            ))

        assert syncer.scan_source.call_count == 1
        scanned_label = syncer.scan_source.call_args[0][0]["label"]
        assert scanned_label == "Accounts"
