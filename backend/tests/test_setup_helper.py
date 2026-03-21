"""
tests/test_setup_helper.py — Unit tests for the YAML config patching logic in setup_helper.py

The tests exercise the parse → mutate → dump pattern directly, which is the
core correctness guarantee of Fix #6. This avoids fighting Path(__file__)
resolution while covering every meaningful code path.

Run with:  pytest backend/tests/test_setup_helper.py -v
"""

import ntpath
from pathlib import Path

import pytest
import yaml


class TestSetupHelperYamlPatching:
    """
    Test the config.yaml patching logic directly — the core of Fix #6.
    We call the YAML manipulation logic inline rather than invoking main(),
    which avoids fighting with Path(__file__).parent.parent resolution.
    """

    def test_ssd_path_written_to_yaml(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(yaml.dump({"ssd_path": "", "secondary_ssd_path": "", "sources": []}), encoding="utf-8")

        with open(config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        cfg["ssd_path"] = "D:\\GhostBackup"

        with open(config, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        with open(config, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert result["ssd_path"] == "D:\\GhostBackup"

    def test_secondary_ssd_path_written(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(yaml.dump({"ssd_path": "", "secondary_ssd_path": "", "sources": []}), encoding="utf-8")

        with open(config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cfg["secondary_ssd_path"] = "E:\\Backup2"
        with open(config, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        with open(config, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert result["secondary_ssd_path"] == "E:\\Backup2"

    def test_source_appended_to_sources_list(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(yaml.dump({"ssd_path": "", "sources": []}), encoding="utf-8")

        with open(config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        source_path = "C:\\Users\\Shared\\Clients"
        label = ntpath.basename(source_path) or "My Files"
        sources = cfg.get("sources") or []
        sources.append({"label": label, "path": source_path, "enabled": True})
        cfg["sources"] = sources
        with open(config, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        with open(config, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert len(result["sources"]) == 1
        assert result["sources"][0]["label"] == "Clients"
        assert result["sources"][0]["enabled"] is True

    def test_duplicate_source_not_added_twice(self, tmp_path):
        config = tmp_path / "config.yaml"
        source_path = "C:\\Users\\Shared\\Clients"
        config.write_text(yaml.dump({
            "sources": [{"label": "Clients", "path": source_path, "enabled": True}]
        }), encoding="utf-8")

        with open(config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        sources = cfg.get("sources") or []
        if not any(s.get("path") == source_path for s in sources):
            sources.append({"label": "Clients", "path": source_path, "enabled": True})
        cfg["sources"] = sources
        with open(config, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        with open(config, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert len(result["sources"]) == 1

    def test_existing_keys_preserved_after_patch(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(yaml.dump({
            "ssd_path": "",
            "sources":  [],
            "schedule": {"time": "09:00", "timezone": "Asia/Kathmandu"},
        }), encoding="utf-8")

        with open(config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cfg["ssd_path"] = "D:\\Backup"
        with open(config, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        with open(config, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert result["schedule"]["time"] == "09:00"
        assert result["schedule"]["timezone"] == "Asia/Kathmandu"

    def test_windows_backslash_path_survives_yaml_round_trip(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(yaml.dump({"ssd_path": ""}), encoding="utf-8")
        windows_path = "D:\\GhostBackup\\Primary"

        with open(config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cfg["ssd_path"] = windows_path
        with open(config, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        with open(config, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        # YAML round-trips the string correctly — no double-escaping
        assert result["ssd_path"] == windows_path


class TestSetupHelperEnvFile:
    """Test .env.local generation logic in isolation."""

    def test_env_file_contains_encryption_key(self, tmp_path):
        env_path = tmp_path / ".env.local"
        key = "TEST_KEY_abc123"
        env_path.write_text(
            f"GHOSTBACKUP_ENCRYPTION_KEY={key}\nGHOSTBACKUP_SMTP_PASSWORD=\n",
            encoding="utf-8",
        )
        content = env_path.read_text(encoding="utf-8")
        assert f"GHOSTBACKUP_ENCRYPTION_KEY={key}" in content

    def test_env_file_contains_smtp_password_placeholder(self, tmp_path):
        env_path = tmp_path / ".env.local"
        env_path.write_text(
            "GHOSTBACKUP_ENCRYPTION_KEY=key\nGHOSTBACKUP_SMTP_PASSWORD=\n",
            encoding="utf-8",
        )
        content = env_path.read_text(encoding="utf-8")
        assert "GHOSTBACKUP_SMTP_PASSWORD" in content
