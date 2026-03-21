"""
test_api.py — Integration tests for the FastAPI endpoints.

All heavy dependencies (ConfigManager, ManifestDB, BackupScheduler, etc.)
are replaced with mocks so tests run without a real SSD or scheduler.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Mock factories ─────────────────────────────────────────────────────────────

def _make_config():
    cfg = MagicMock()
    cfg.ssd_path = "/tmp/test_ssd"
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
    w.status.return_value = {"running": False, "sources": []}
    return w


# ── Client fixture ─────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """
    TestClient with all backend services replaced by mocks.
    Mocks the constructors so the real lifespan runs without touching disk.
    """
    mock_cfg  = _make_config()
    mock_mani = _make_manifest()
    mock_rep  = _make_reporter()
    mock_sync = _make_syncer()
    mock_sched = _make_scheduler()
    mock_watch = _make_watcher()

    with (
        patch("api.ConfigManager",    return_value=mock_cfg),
        patch("api.ManifestDB",       return_value=mock_mani),
        patch("api.Reporter",         return_value=mock_rep),
        patch("api.LocalSyncer",      return_value=mock_sync),
        patch("api.BackupScheduler",  return_value=mock_sched),
        patch("api.FileWatcher",      return_value=mock_watch),
        patch("api.get_ssd_status",   return_value={"status": "ok"}),
    ):
        import api as api_module
        with TestClient(api_module.app, raise_server_exceptions=True) as c:
            c._api = api_module   # expose for tests that need to set _active_run
            yield c


# ── /health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_no_auth_required(self, client):
        # /health must not require X-API-Key
        r = client.get("/health")
        assert r.status_code == 200

    def test_reports_scheduler_running(self, client):
        assert client.get("/health").json()["scheduler_running"] is True

    def test_reports_encryption_active(self, client):
        assert client.get("/health").json()["encryption_active"] is True

    def test_includes_schedule_metadata(self, client):
        data = client.get("/health").json()
        assert data["schedule"]["time"] == "08:00"
        assert data["schedule"]["timezone"] == "Europe/London"


# ── Auth middleware ────────────────────────────────────────────────────────────

class TestAuth:
    def test_no_token_env_allows_all(self, client):
        os.environ.pop("GHOSTBACKUP_API_TOKEN", None)
        assert client.get("/run/status").status_code == 200

    def test_wrong_key_rejected(self, client, monkeypatch):
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "correct-token")
        r = client.get("/run/status", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_correct_key_accepted(self, client, monkeypatch):
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "correct-token")
        r = client.get("/run/status", headers={"X-API-Key": "correct-token"})
        assert r.status_code == 200

    def test_health_bypasses_auth(self, client, monkeypatch):
        monkeypatch.setenv("GHOSTBACKUP_API_TOKEN", "secret")
        # No X-API-Key header — should still be 200
        assert client.get("/health").status_code == 200


# ── /run/status ────────────────────────────────────────────────────────────────

class TestRunStatus:
    def test_idle_when_no_active_run(self, client):
        client._api._active_run = None
        assert client.get("/run/status").json()["status"] == "idle"

    def test_returns_active_run(self, client):
        client._api._active_run = {"status": "running", "run_id": 7}
        r = client.get("/run/status")
        assert r.json()["status"] == "running"
        assert r.json()["run_id"] == 7


# ── /run/start ─────────────────────────────────────────────────────────────────

class TestRunStart:
    def test_starts_backup(self, client):
        client._api._active_run = None
        r = client.post("/run/start", json={"full": False, "sources": []})
        assert r.status_code == 200
        assert "started" in r.json()["message"].lower()

    def test_rejects_concurrent_run(self, client):
        client._api._active_run = {"status": "running"}
        assert client.post("/run/start", json={}).status_code == 409


# ── /run/stop ──────────────────────────────────────────────────────────────────

class TestRunStop:
    def test_cancels_running_job(self, client):
        client._api._active_run = {"status": "running"}
        r = client.post("/run/stop")
        assert r.status_code == 200
        assert client._api._active_run["status"] == "cancelled"

    def test_error_when_no_active_run(self, client):
        client._api._active_run = None
        assert client.post("/run/stop").status_code == 400


# ── /runs ──────────────────────────────────────────────────────────────────────

class TestRuns:
    def test_returns_run_list(self, client):
        import api as api_module
        api_module._manifest.get_runs.return_value = [{"run_id": 1, "status": "success"}]
        r = client.get("/runs")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_run_not_found_returns_404(self, client):
        import api as api_module
        api_module._manifest.get_run.return_value = None
        assert client.get("/runs/999").status_code == 404

    def test_run_logs_endpoint(self, client):
        import api as api_module
        api_module._manifest.get_run.return_value = {"run_id": 1}
        api_module._manifest.get_logs.return_value = [{"level": "INFO", "msg": "ok"}]
        r = client.get("/runs/1/logs")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ── /config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_get_config(self, client):
        r = client.get("/config")
        assert r.status_code == 200
        assert "ssd_path" in r.json()

    def test_get_audit_trail(self, client):
        import api as api_module
        api_module._manifest.get_config_audit.return_value = [{"field": "ssd_path", "old": "", "new": "D:\\"}]
        r = client.get("/config/audit")
        assert r.status_code == 200
        assert len(r.json()) == 1


    def test_update_site_persists_enabled_state_and_reloads_watcher(self, client):
        import api as api_module
        api_module._config.update_site.return_value = {
            "label": "Accounts", "path": "/data/accounts", "enabled": False,
        }
        r = client.patch("/config/sites/Accounts", json={"enabled": False})
        assert r.status_code == 200
        api_module._config.update_site.assert_called_once_with("Accounts", {"enabled": False})
        api_module._watcher.reload_sources.assert_called()
        assert r.json()["source"]["enabled"] is False

    def test_add_site_returns_canonical_config(self, client):
        import api as api_module
        api_module._config.add_site.return_value = {
            "label": "Accounts", "path": "/data/accounts", "enabled": True,
        }
        api_module._config.to_dict_safe.return_value = {
            "ssd_path": "/tmp/test_ssd",
            "sources": [{"label": "Accounts", "path": "/data/accounts", "enabled": True}],
        }
        r = client.post("/config/sites", json={"label": "Accounts", "path": "/data/accounts", "enabled": True})
        assert r.status_code == 200
        assert r.json()["source"]["label"] == "Accounts"
        assert r.json()["config"]["sources"][0]["label"] == "Accounts"
        api_module._watcher.reload_sources.assert_called()

    def test_remove_site_returns_updated_config(self, client):
        import api as api_module
        api_module._config.remove_site.return_value = True
        api_module._config.to_dict_safe.return_value = {
            "ssd_path": "/tmp/test_ssd",
            "sources": [],
        }
        r = client.delete("/config/sites/Accounts")
        assert r.status_code == 200
        assert r.json()["config"]["sources"] == []
        api_module._watcher.reload_sources.assert_called()

    def test_remove_site_returns_404_when_missing(self, client):
        import api as api_module
        api_module._config.remove_site.return_value = False
        assert client.delete("/config/sites/Missing").status_code == 404


class TestRestore:
    def test_dry_run_returns_file_list(self, client):
        import api as api_module
        api_module._manifest.get_run.return_value = {"run_id": 1, "status": "success"}
        api_module._manifest.get_files.return_value = [
            {"name": "invoice.xlsx", "size": 2048, "backup_path": "/ssd/invoice.xlsx"}
        ]
        r = client.post("/restore", json={
            "run_id": 1, "library": "Clients",
            "destination": "C:\\Restore", "dry_run": True,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["dry_run"] is True
        assert data["files_to_restore"] == 1
        assert data["files"][0]["name"] == "invoice.xlsx"

    def test_restore_from_failed_run_rejected(self, client):
        import api as api_module
        api_module._manifest.get_run.return_value = {"run_id": 1, "status": "failed"}
        r = client.post("/restore", json={
            "run_id": 1, "library": "Clients",
            "destination": "C:\\Restore", "dry_run": True,
        })
        assert r.status_code == 400

    def test_restore_run_not_found(self, client):
        import api as api_module
        api_module._manifest.get_run.return_value = None
        assert client.post("/restore", json={
            "run_id": 999, "library": "X",
            "destination": "C:\\Restore", "dry_run": True,
        }).status_code == 404

    def test_restore_no_files_returns_404(self, client):
        import api as api_module
        api_module._manifest.get_run.return_value = {"run_id": 1, "status": "success"}
        api_module._manifest.get_files.return_value = []
        assert client.post("/restore", json={
            "run_id": 1, "library": "Empty",
            "destination": "C:\\Restore", "dry_run": True,
        }).status_code == 404


# ── /alerts ────────────────────────────────────────────────────────────────────

class TestAlerts:
    def test_returns_alert_list(self, client):
        import api as api_module
        api_module._reporter.alerts.get_all.return_value = [{"id": 1, "title": "SSD full"}]
        api_module._reporter.alerts.unread_count.return_value = 1
        r = client.get("/alerts")
        assert r.status_code == 200
        assert r.json()["unread_count"] == 1

    def test_dismiss_alert(self, client):
        import api as api_module
        api_module._reporter.alerts.dismiss.return_value = True
        r = client.post("/alerts/1/dismiss")
        assert r.status_code == 200
        assert r.json()["dismissed"] == 1

    def test_dismiss_missing_alert_returns_404(self, client):
        import api as api_module
        api_module._reporter.alerts.dismiss.return_value = False
        assert client.post("/alerts/999/dismiss").status_code == 404

    def test_dismiss_all(self, client):
        import api as api_module
        api_module._reporter.alerts.dismiss_all.return_value = 3
        r = client.post("/alerts/dismiss-all")
        assert r.status_code == 200
        assert r.json()["dismissed"] == 3


# ── /settings/retention ────────────────────────────────────────────────────────

class TestRetention:
    def test_update_retention(self, client):
        import api as api_module
        api_module._config.update_retention = MagicMock()
        r = client.patch("/settings/retention", json={
            "daily_days": 365, "weekly_days": 2555, "guard_days": 7,
        })
        assert r.status_code == 200

    def test_rejects_retention_below_minimum(self, client):
        import api as api_module
        api_module._config.update_retention = MagicMock(
            side_effect=ValueError("retention below 7-year compliance minimum")
        )
        r = client.patch("/settings/retention", json={
            "daily_days": 1, "weekly_days": 7, "guard_days": 1,
        })
        assert r.status_code == 400


# ── /verify ────────────────────────────────────────────────────────────────────

class TestVerify:
    def test_verify_rejected_while_backup_running(self, client):
        client._api._active_run = {"status": "running"}
        assert client.post("/verify").status_code == 409

    def test_verify_accepted_when_idle(self, client):
        client._api._active_run = None
        r = client.post("/verify")
        assert r.status_code == 200
        assert "started" in r.json()["message"].lower()


# ── /watcher ───────────────────────────────────────────────────────────────────

class TestWatcher:
    def test_watcher_status(self, client):
        r = client.get("/watcher/status")
        assert r.status_code == 200

    def test_watcher_stop_when_not_running(self, client):
        import api as api_module
        api_module._watcher._running = False
        r = client.post("/watcher/stop")
        assert r.status_code == 200

    def test_watcher_start_no_sources(self, client):
        import api as api_module
        api_module._config.get_enabled_sources.return_value = []
        api_module._watcher._running = False
        assert client.post("/watcher/start").status_code == 400


# ── /settings/encryption/generate-key ─────────────────────────────────────────



def test_retry_locked_files_uses_stored_file_meta(monkeypatch):
    import api as api_module

    api_module._active_run = {
        "errors": [{
            "file": "invoice.xlsx",
            "library": "Accounts",
            "error": "Permission denied",
            "original_path": "/data/accounts/invoice.xlsx",
            "file_meta": {
                "source_label": "Accounts",
                "name": "invoice.xlsx",
                "original_path": "/data/accounts/invoice.xlsx",
                "rel_path": "invoice.xlsx",
                "size": 10,
                "mtime": 123.0,
                "xxhash": "abc",
            },
        }],
        "files_transferred": 0,
        "files_failed": 1,
    }
    api_module._syncer.copy_file.return_value = "/ssd/invoice.xlsx"

    import asyncio
    asyncio.run(api_module._retry_locked_files(7))

    api_module._syncer.copy_file.assert_called_once()
    api_module._manifest.record_file.assert_called_once_with(
        7,
        api_module._active_run["errors"][0]["file_meta"],
        "/ssd/invoice.xlsx",
    )
    assert api_module._active_run["files_transferred"] == 1
    assert api_module._active_run["files_failed"] == 0
    assert api_module._active_run["errors"][0]["retry_succeeded"] is True


def test_main_uses_env_port(monkeypatch):
    import runpy

    monkeypatch.setenv("GHOSTBACKUP_API_PORT", "9876")
    with patch("uvicorn.run") as mock_run:
        runpy.run_module("api", run_name="__main__")

    assert mock_run.call_args.kwargs["port"] == 9876


class TestEncryptionKey:
    def test_generate_key_returns_200(self, client):
        r = client.post("/settings/encryption/generate-key")
        assert r.status_code == 200

    def test_generate_key_returns_key_field(self, client):
        r = client.post("/settings/encryption/generate-key")
        data = r.json()
        assert "key" in data

    def test_generate_key_is_non_empty_string(self, client):
        r = client.post("/settings/encryption/generate-key")
        key = r.json()["key"]
        assert isinstance(key, str)
        assert len(key) > 0

    def test_generate_key_is_valid_fernet_key(self, client):
        """The returned key must be usable by Fernet — base64url, 32 raw bytes."""
        from cryptography.fernet import Fernet
        r   = client.post("/settings/encryption/generate-key")
        key = r.json()["key"].encode()
        f = Fernet(key)
        token = f.encrypt(b"test")
        assert f.decrypt(token) == b"test"

    def test_generate_key_differs_each_call(self, client):
        key1 = client.post("/settings/encryption/generate-key").json()["key"]
        key2 = client.post("/settings/encryption/generate-key").json()["key"]
        assert key1 != key2
