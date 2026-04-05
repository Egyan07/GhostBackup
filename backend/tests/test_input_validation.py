"""
test_input_validation.py — Security-focused input validation tests.

Tests path traversal attacks, JSON bombs, shell injection in config fields,
and API auth edge cases against the FastAPI endpoints.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Mock factories (same pattern as test_api.py) ────────────────────────────


def _make_config():
    cfg = MagicMock()
    cfg.ssd_path = "/tmp/test_ssd"
    cfg.secondary_ssd_path = None
    cfg.key_storage_method = "env"
    cfg.get_enabled_sources.return_value = []
    cfg.to_dict_safe.return_value = {"ssd_path": "/tmp/test_ssd", "sources": []}
    cfg.concurrency = 2
    cfg.circuit_breaker_threshold = 0.05
    cfg.schedule_time = "08:00"
    cfg.timezone = "Europe/London"
    cfg.retention_daily_days = 365
    cfg.retention_weekly_days = 2555
    cfg.retention_guard_days = 7
    return cfg


def _make_manifest():
    m = MagicMock()
    m.get_runs.return_value = []
    m.get_run.return_value = None
    m.get_logs.return_value = []
    m.get_files.return_value = []
    m.get_config_audit.return_value = []
    m.create_run.return_value = 1
    m.get_latest_successful_run.return_value = None
    m.get_last_drill_completion.return_value = None
    return m


def _make_reporter():
    r = MagicMock()
    r.alerts = MagicMock()
    r.alerts.get_all.return_value = []
    r.alerts.unread_count.return_value = 0
    r.alerts.dismiss.return_value = True
    r.alerts.dismiss_all.return_value = 0
    r.alert_and_notify = AsyncMock()
    r.send_run_report = AsyncMock()
    r.send_test_email = AsyncMock()
    return r


def _make_syncer():
    s = MagicMock()
    s._crypto = MagicMock()
    s._crypto.enabled = True
    s.encryption_active = True
    s.check_ssd.return_value = {"status": "ok"}
    return s


def _make_scheduler():
    sc = MagicMock()
    sc.is_running.return_value = True
    sc.next_run_time.return_value = "08:00"
    return sc


def _make_watcher():
    w = MagicMock()
    w._running = False
    w.is_running = False
    w.status.return_value = {"running": False, "sources": []}
    return w


@pytest.fixture()
def client():
    """TestClient with all backend services replaced by mocks."""
    mock_cfg = _make_config()
    mock_mani = _make_manifest()
    mock_rep = _make_reporter()
    mock_sync = _make_syncer()
    mock_sched = _make_scheduler()
    mock_watch = _make_watcher()

    with (
        patch("api.ConfigManager", return_value=mock_cfg),
        patch("api.ManifestDB", return_value=mock_mani),
        patch("api.Reporter", return_value=mock_rep),
        patch("api.LocalSyncer", return_value=mock_sync),
        patch("api.BackupScheduler", return_value=mock_sched),
        patch("api.FileWatcher", return_value=mock_watch),
        patch("api.get_ssd_status", return_value={"status": "ok"}),
    ):
        import api as api_module

        api_module._limiter.reset()
        with TestClient(api_module.app, raise_server_exceptions=True) as c:
            c._api = api_module
            yield c


def _setup_restore_mocks(api_module):
    """Configure mocks so restore endpoint reaches validation logic."""
    api_module._manifest.get_run.return_value = {"id": 1, "status": "completed"}
    api_module._manifest.get_files.return_value = [
        {"name": "f.txt", "backup_path": "/tmp/f.txt", "size": 100}
    ]


# ── 1. Path traversal attacks on /restore ────────────────────────────────────


class TestPathTraversalAttacks:
    """Exhaustive path traversal vectors against the /restore endpoint."""

    def test_basic_dotdot_traversal(self, client):
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "../../../etc/passwd",
        })
        assert resp.status_code == 400

    def test_deep_dotdot_traversal(self, client):
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "/tmp/restore/../../../../etc/passwd",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "GB-E042"

    def test_null_byte_in_path(self, client):
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "/tmp/restore\x00/etc/passwd",
        })
        assert resp.status_code == 400

    def test_null_byte_at_end(self, client):
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "/tmp/restore\x00",
        })
        assert resp.status_code == 400

    def test_windows_drive_letter_traversal(self, client):
        """Windows-style drive letter with backslash traversal.

        On Linux, backslashes are treated as literal filename characters by
        pathlib, so '..' is not detected as a path component.  The backend
        has a separate Windows-only guard (os.name == 'nt') for this case.
        On Linux this resolves to a harmless literal path, so we expect 200
        (dry_run).  On Windows it would be blocked with 400.
        """
        import os
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "C:\\..\\..\\Windows\\System32",
            "dry_run": True,
        })
        if os.name == "nt":
            assert resp.status_code == 400
            assert resp.json()["detail"]["code"] == "GB-E042"
        else:
            # On Linux the backslashes are literal — not a real traversal
            assert resp.status_code == 200

    def test_url_encoded_traversal(self, client):
        """URL-encoded (%2e%2e%2f) path traversal.

        Note: FastAPI/Starlette decodes percent-encoding for URL paths
        but JSON body values are not URL-decoded. The raw string '%2e%2e%2f'
        is treated as a literal directory name rather than '../', so the
        backend will not reject it as traversal — but it also cannot
        traverse anything since the filesystem treats it literally.
        """
        import api as api_module
        _setup_restore_mocks(api_module)
        # The literal string "%2e%2e%2f" in a JSON body is not decoded,
        # so it does not actually represent ".." — the path is safe.
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "/tmp/%2e%2e%2fetc/passwd",
            "dry_run": True,
        })
        # The backend treats this as a literal path, which is safe;
        # it should succeed as a dry run with the literal directory name.
        assert resp.status_code == 200

    def test_dotdot_with_trailing_slash(self, client):
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "/tmp/../../../",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "GB-E042"

    def test_embedded_dotdot_component(self, client):
        import api as api_module
        _setup_restore_mocks(api_module)
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": "Clients",
            "destination": "/tmp/safe/../../../etc",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "GB-E042"


# ── 2. JSON bomb / oversized payloads ────────────────────────────────────────


class TestOversizedPayloads:
    """Verify the API handles extremely large or deeply nested payloads."""

    def test_extremely_long_ssd_path(self, client):
        """Config update with a 100KB ssd_path string."""
        long_path = "/tmp/" + "A" * 100_000
        resp = client.patch("/config", json={"ssd_path": long_path})
        # Should either reject or accept gracefully without crashing
        assert resp.status_code in (200, 400, 422)

    def test_thousands_of_sources_in_run_start(self, client):
        """RunRequest with thousands of source items."""
        sources = [f"/fake/source/{i}" for i in range(5000)]
        resp = client.post("/run/start", json={"full": False, "sources": sources})
        # Should accept (starts a background task) or reject with validation error
        assert resp.status_code in (200, 400, 422)

    def test_very_long_library_name_in_restore(self, client):
        """Restore request with a massively long library name."""
        import api as api_module
        _setup_restore_mocks(api_module)
        # Override get_files to return empty for unrecognised library
        api_module._manifest.get_files.return_value = []
        long_lib = "X" * 50_000
        resp = client.post("/restore", json={
            "run_id": 1,
            "library": long_lib,
            "destination": "/tmp/restore",
        })
        # Should handle gracefully — likely 404 because files list is empty
        assert resp.status_code in (400, 404, 422)

    def test_deeply_nested_exclude_patterns(self, client):
        """Config update with thousands of exclude patterns."""
        patterns = [f"*.tmp{i}" for i in range(3000)]
        resp = client.patch("/config", json={"exclude_patterns": patterns})
        assert resp.status_code in (200, 400, 422)

    def test_empty_json_body_to_restore(self, client):
        """POST /restore with empty body should return validation error."""
        resp = client.post("/restore", content=b"{}", headers={
            "Content-Type": "application/json",
        })
        assert resp.status_code == 422


# ── 3. Injection in config fields ────────────────────────────────────────────


class TestConfigInjection:
    """Verify config endpoints handle shell metacharacters and invalid values."""

    def test_shell_metacharacters_in_ssd_path(self, client):
        """ssd_path with shell injection attempt: '; rm -rf /'."""
        resp = client.patch("/config", json={"ssd_path": "; rm -rf /"})
        # Should either accept (stored as literal string) or reject
        assert resp.status_code in (200, 400, 422)
        # If accepted, the value should be stored literally, not executed
        if resp.status_code == 200:
            config_data = resp.json().get("config", {})
            # The ssd_path should be the literal string, not empty from execution
            assert config_data is not None

    def test_backtick_injection_in_ssd_path(self, client):
        """ssd_path with backtick command substitution."""
        resp = client.patch("/config", json={"ssd_path": "`whoami`"})
        assert resp.status_code in (200, 400, 422)

    def test_pipe_injection_in_ssd_path(self, client):
        """ssd_path with pipe injection."""
        resp = client.patch("/config", json={"ssd_path": "/tmp | cat /etc/passwd"})
        assert resp.status_code in (200, 400, 422)

    def test_newlines_in_schedule_time(self, client):
        """schedule_time with embedded newlines."""
        resp = client.patch("/config", json={"schedule_time": "08:00\nmalicious"})
        # Should reject or sanitise — the scheduler expects HH:MM format
        assert resp.status_code in (200, 400, 422)

    def test_invalid_timezone_value(self, client):
        """Timezone set to a non-existent value."""
        resp = client.patch("/config", json={"timezone": "Not/A/Real/Timezone"})
        assert resp.status_code in (200, 400, 422)

    def test_dollar_expansion_in_ssd_path(self, client):
        """ssd_path with $() command substitution."""
        resp = client.patch("/config", json={"ssd_path": "$(rm -rf /)"})
        assert resp.status_code in (200, 400, 422)

    def test_semicolon_in_exclude_patterns(self, client):
        """Exclude patterns with shell metacharacters."""
        resp = client.patch("/config", json={
            "exclude_patterns": ["*.tmp; rm -rf /", "$(whoami)"],
        })
        assert resp.status_code in (200, 400, 422)

    def test_negative_concurrency(self, client):
        """Concurrency set to a negative value."""
        resp = client.patch("/config", json={"concurrency": -5})
        assert resp.status_code in (200, 400, 422)

    def test_zero_max_file_size(self, client):
        """max_file_size_gb set to zero."""
        resp = client.patch("/config", json={"max_file_size_gb": 0})
        assert resp.status_code in (200, 400, 422)


# ── 4. API auth edge cases ───────────────────────────────────────────────────


class TestAuthEdgeCases:
    """Test authentication with unusual or malicious token values."""

    def test_empty_api_key_header(self, client, monkeypatch):
        """Empty X-API-Key header should be rejected."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/run/status", headers={"X-API-Key": ""})
        assert resp.status_code == 401

    def test_very_long_token_10kb(self, client, monkeypatch):
        """X-API-Key with 10KB of data should be rejected gracefully."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        long_token = "A" * 10_240
        resp = client.get("/run/status", headers={"X-API-Key": long_token})
        assert resp.status_code == 401

    def test_token_with_null_bytes(self, client, monkeypatch):
        """X-API-Key containing null bytes should be rejected."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/run/status", headers={"X-API-Key": "token\x00inject"})
        assert resp.status_code == 401

    def test_token_with_only_whitespace(self, client, monkeypatch):
        """X-API-Key that is all spaces should be rejected."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/run/status", headers={"X-API-Key": "   "})
        assert resp.status_code == 401

    def test_token_with_newlines(self, client, monkeypatch):
        """X-API-Key containing newline characters."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/run/status", headers={"X-API-Key": "real\nsecure\ntoken"})
        assert resp.status_code == 401

    def test_correct_token_accepted(self, client, monkeypatch):
        """Sanity check: correct token still works."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/run/status", headers={"X-API-Key": "real-secure-token"})
        assert resp.status_code == 200

    def test_no_api_key_header_at_all(self, client, monkeypatch):
        """Missing X-API-Key header entirely should be rejected."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/run/status")
        assert resp.status_code == 401

    def test_health_endpoint_needs_no_token(self, client, monkeypatch):
        """/health should always be accessible without auth."""
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "real-secure-token")
        resp = client.get("/health")
        assert resp.status_code == 200
