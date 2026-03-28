"""
tests/test_config.py — Unit tests for ConfigManager

Run with:  pytest backend/tests/test_config.py -v
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock

from config import ConfigManager, _deep_merge


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg(tmp_path):
    """ConfigManager with a temporary config file."""
    return ConfigManager(config_path=tmp_path / "config.yaml")


# ── Defaults ──────────────────────────────────────────────────────────────────

def test_creates_default_config_when_file_missing(tmp_path):
    cfg = ConfigManager(config_path=tmp_path / "new.yaml")
    assert cfg.schedule_time == "08:00"
    assert cfg.timezone == "Europe/London"


def test_default_config_file_is_written(tmp_path):
    config_file = tmp_path / "new.yaml"
    ConfigManager(config_path=config_file)
    assert config_file.exists()


def test_default_circuit_breaker_threshold(cfg):
    assert cfg.circuit_breaker_threshold == 0.05


def test_default_compliance_years(cfg):
    assert cfg.compliance_years == 7


def test_default_compliance_min_days(cfg):
    assert cfg.compliance_min_days == 7 * 365


def test_default_retention_guard_days_minimum(cfg):
    assert cfg.retention_guard_days >= 7


def test_default_verify_checksums_enabled(cfg):
    assert cfg.verify_checksums is True


def test_default_chunk_size_bytes(cfg):
    assert cfg.chunk_size_bytes == 4 * 1024 * 1024


def test_default_max_file_size_bytes(cfg):
    assert cfg.max_file_size_bytes == 5 * 1024 ** 3


# ── Secrets / encryption ──────────────────────────────────────────────────────

def test_encryption_key_none_when_env_not_set(cfg, monkeypatch):
    monkeypatch.delenv("GHOSTBACKUP_ENCRYPTION_KEY", raising=False)
    assert cfg.encryption_key is None


def test_encryption_key_returns_bytes_when_set(cfg, monkeypatch):
    monkeypatch.setenv("GHOSTBACKUP_ENCRYPTION_KEY", "testkey123")
    assert cfg.encryption_key == b"testkey123"


def test_encryption_enabled_false_without_key(cfg, monkeypatch):
    monkeypatch.delenv("GHOSTBACKUP_ENCRYPTION_KEY", raising=False)
    assert cfg.encryption_enabled is False


def test_encryption_enabled_true_with_key(cfg, monkeypatch):
    monkeypatch.setenv("GHOSTBACKUP_ENCRYPTION_KEY", "testkey123")
    assert cfg.encryption_enabled is True


def test_encryption_enabled_false_when_disabled_in_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOSTBACKUP_ENCRYPTION_KEY", "testkey123")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"encryption": {"enabled": False}}))
    cfg = ConfigManager(config_path=config_file)
    assert cfg.encryption_enabled is False


def test_smtp_password_from_env(cfg, monkeypatch):
    monkeypatch.setenv("GHOSTBACKUP_SMTP_PASSWORD", "secret123")
    assert cfg.smtp_password == "secret123"


def test_smtp_password_empty_when_not_set(cfg, monkeypatch):
    monkeypatch.delenv("GHOSTBACKUP_SMTP_PASSWORD", raising=False)
    assert cfg.smtp_password == ""


# ── Sources ───────────────────────────────────────────────────────────────────

def test_add_site(cfg):
    cfg.add_site({"label": "Accounts", "path": "/data/accounts"})
    sources = cfg.get_enabled_sources()
    assert len(sources) == 1
    assert sources[0]["label"] == "Accounts"


def test_add_site_duplicate_raises(cfg):
    cfg.add_site({"label": "Accounts", "path": "/data/accounts"})
    with pytest.raises(ValueError, match="already exists"):
        cfg.add_site({"label": "Accounts", "path": "/data/other"})


def test_add_site_missing_label_raises(cfg):
    with pytest.raises(ValueError, match="label"):
        cfg.add_site({"path": "/data/accounts"})


def test_add_site_missing_path_raises(cfg):
    with pytest.raises(ValueError, match="path"):
        cfg.add_site({"label": "Accounts"})


def test_add_site_disabled_by_default_is_false(cfg):
    cfg.add_site({"label": "Accounts", "path": "/data/accounts", "enabled": False})
    assert cfg.get_enabled_sources() == []


def test_remove_site_returns_true(cfg):
    cfg.add_site({"label": "Accounts", "path": "/data/accounts"})
    assert cfg.remove_site("Accounts") is True
    assert cfg.get_enabled_sources() == []


def test_remove_site_not_found_returns_false(cfg):
    assert cfg.remove_site("Nonexistent") is False




def test_update_site_toggles_enabled_state(cfg):
    cfg.add_site({"label": "Accounts", "path": "/data/accounts"})
    updated = cfg.update_site("Accounts", {"enabled": False})
    assert updated["enabled"] is False
    assert cfg.get_enabled_sources() == []


def test_update_site_missing_source_raises(cfg):
    with pytest.raises(ValueError, match="not found"):
        cfg.update_site("Missing", {"enabled": False})


# ── Updates ───────────────────────────────────────────────────────────────────

def test_update_ssd_path(cfg):
    cfg.update({"ssd_path": "/mnt/backup"})
    assert cfg.ssd_path == "/mnt/backup"


def test_update_logs_changed_value_to_audit(cfg):
    manifest = MagicMock()
    cfg.set_manifest(manifest)
    cfg.update({"ssd_path": "/mnt/backup"})
    manifest.log_config_change.assert_called_once_with("ssd_path", "", "/mnt/backup")


def test_update_skips_unchanged_values(cfg):
    manifest = MagicMock()
    cfg.set_manifest(manifest)
    cfg.update({"schedule_time": "08:00"})  # same as default
    manifest.log_config_change.assert_not_called()


def test_update_unknown_key_is_ignored(cfg):
    cfg.update({"nonexistent_key": "value"})  # should not raise


def test_update_circuit_breaker_threshold(cfg):
    cfg.update({"circuit_breaker_threshold": 0.10})
    assert cfg.circuit_breaker_threshold == 0.10


# ── Retention ─────────────────────────────────────────────────────────────────

def test_update_retention_valid(cfg):
    cfg.update_retention({"daily_days": 180, "weekly_days": 2555, "guard_days": 7})
    assert cfg.retention_daily_days == 180


def test_update_retention_rejects_below_compliance(cfg):
    with pytest.raises(ValueError, match="compliance minimum"):
        cfg.update_retention({"daily_days": 365, "weekly_days": 100})


def test_update_retention_rejects_guard_below_7(cfg):
    with pytest.raises(ValueError, match="guard_days"):
        cfg.update_retention({
            "daily_days": 365, "weekly_days": 2555, "guard_days": 3,
        })


def test_update_retention_rejects_daily_exceeds_weekly(cfg):
    with pytest.raises(ValueError, match="daily_days cannot exceed"):
        cfg.update_retention({"daily_days": 3000, "weekly_days": 2555})


def test_update_retention_logs_to_audit(cfg):
    manifest = MagicMock()
    cfg.set_manifest(manifest)
    cfg.update_retention({"daily_days": 180, "weekly_days": 2555, "guard_days": 7})
    manifest.log_config_change.assert_called_once()


# ── _validate_update ─────────────────────────────────────────────────────────

def test_validate_update_rejects_bad_schedule_time(cfg):
    with pytest.raises(ValueError, match="schedule_time"):
        cfg.update({"schedule_time": "25:00"})


def test_validate_update_rejects_invalid_timezone(cfg):
    with pytest.raises(ValueError, match="timezone"):
        cfg.update({"timezone": "Mars/Phobos"})


def test_validate_update_rejects_concurrency_out_of_range(cfg):
    with pytest.raises(ValueError, match="concurrency"):
        cfg.update({"concurrency": 0})
    with pytest.raises(ValueError, match="concurrency"):
        cfg.update({"concurrency": 33})


def test_validate_update_rejects_max_file_size_out_of_range(cfg):
    with pytest.raises(ValueError, match="max_file_size_gb"):
        cfg.update({"max_file_size_gb": 0})
    with pytest.raises(ValueError, match="max_file_size_gb"):
        cfg.update({"max_file_size_gb": 101})


def test_validate_update_rejects_circuit_breaker_out_of_range(cfg):
    with pytest.raises(ValueError, match="circuit_breaker_threshold"):
        cfg.update({"circuit_breaker_threshold": -0.1})
    with pytest.raises(ValueError, match="circuit_breaker_threshold"):
        cfg.update({"circuit_breaker_threshold": 1.1})


def test_validate_update_rejects_bad_exclude_patterns(cfg):
    with pytest.raises(ValueError, match="exclude_patterns"):
        cfg.update({"exclude_patterns": "*.tmp"})


def test_validate_update_accepts_valid_values(cfg):
    cfg.update({
        "schedule_time": "09:30",
        "timezone": "UTC",
        "concurrency": 8,
        "max_file_size_gb": 10,
        "circuit_breaker_threshold": 0.1,
        "exclude_patterns": ["*.tmp", "~$*"],
    })
    assert cfg.schedule_time == "09:30"
    assert cfg.timezone == "UTC"
    assert cfg.concurrency == 8


# ── Safe export ───────────────────────────────────────────────────────────────

def test_to_dict_safe_excludes_smtp_password(cfg):
    safe = cfg.to_dict_safe()
    assert "password" not in safe.get("smtp", {})


def test_to_dict_safe_includes_encryption_active(cfg, monkeypatch):
    monkeypatch.delenv("GHOSTBACKUP_ENCRYPTION_KEY", raising=False)
    safe = cfg.to_dict_safe()
    assert "encryption_active" in safe
    assert safe["encryption_active"] is False


def test_to_dict_safe_includes_compliance_min_days(cfg):
    safe = cfg.to_dict_safe()
    assert safe["compliance_min_days"] == 7 * 365


# ── Deep merge ────────────────────────────────────────────────────────────────

def test_deep_merge_partial_override_preserves_other_keys(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"schedule": {"time": "09:30"}}))
    cfg = ConfigManager(config_path=config_file)
    assert cfg.schedule_time == "09:30"
    assert cfg.timezone == "Europe/London"  # default preserved


def test_deep_merge_top_level_override(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"ssd_path": "/mnt/ssd1"}))
    cfg = ConfigManager(config_path=config_file)
    assert cfg.ssd_path == "/mnt/ssd1"


def test_deep_merge_utility_merges_dicts():
    base     = {"a": {"x": 1, "y": 2}, "b": 10}
    override = {"a": {"x": 99},        "b": 20}
    _deep_merge(base, override)
    assert base["a"]["x"] == 99
    assert base["a"]["y"] == 2
    assert base["b"] == 20


def test_deep_merge_does_not_return_value():
    base = {"a": 1}
    result = _deep_merge(base, {"b": 2})
    assert result is None


# ── SMTP ──────────────────────────────────────────────────────────────────────

def test_update_smtp_does_not_persist_password(cfg):
    cfg.update_smtp({
        "host": "smtp.gmail.com", "port": 587,
        "user": "test@test.com",  "password": "should_not_be_saved",
    })
    safe = cfg.to_dict_safe()
    assert "password" not in safe.get("smtp", {})


def test_update_smtp_does_not_mutate_caller_dict(cfg):
    """update_smtp() must not remove 'password' from the dict the caller passed in."""
    caller_dict = {
        "host": "smtp.gmail.com", "port": 587,
        "user": "test@test.com",  "password": "original_secret",
    }
    cfg.update_smtp(caller_dict)
    assert "password" in caller_dict
    assert caller_dict["password"] == "original_secret"
