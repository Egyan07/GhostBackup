"""
config.py — GhostBackup Configuration Manager

Loads configuration from a YAML file, provides typed property access,
and enforces compliance constraints. Secrets (SMTP password, encryption key)
are read exclusively from environment variables and never persisted to disk.
"""

import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Optional
from zoneinfo import available_timezones

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("config")

CONFIG_PATH = Path(os.getenv("GHOSTBACKUP_CONFIG", "config/config.yaml"))

DEFAULTS: dict = {
    "ssd_path":           "",
    "secondary_ssd_path": "",

    "encryption": {
        "enabled": True,
    },

    "schedule": {
        "time":                "08:00",
        "timezone":            "Europe/London",
        "max_job_minutes":     240,
        "retry_count":         3,
        "retry_delay_minutes": 30,
    },

    "performance": {
        "concurrency":      4,
        "max_file_size_gb": 5,
        "chunk_size_mb":    4,
    },

    "backup": {
        "verify_checksums": True,
        "version_count":    5,
        "exclude_patterns": [
            "~$*", "*.tmp", "Thumbs.db", ".DS_Store",
            "desktop.ini", "*.lnk", "pagefile.sys", "hiberfil.sys",
            "node_modules", ".git", "__pycache__", "*.pyc",
            ".venv", "venv", ".env",
        ],
    },

    "retention": {
        "daily_days":       365,
        "weekly_days":      2555,
        "compliance_years": 7,
        "guard_days":       7,
    },

    "smtp": {
        "host":       "smtp.office365.com",
        "port":       587,
        "use_tls":    True,
        "user":       "",
        "recipients": [],
    },

    "logging": {
        "level":          "INFO",
        "retention_days": 365,
        "log_dir":        "logs",
    },

    "sources": [],

    "circuit_breaker_threshold": 0.05,

    "watcher": {
        "debounce_seconds": 15,
        "cooldown_seconds": 120,
    },
}


class SourceConfig(BaseModel):
    """Validated representation of a single backup source folder."""
    label:   str
    path:    str
    enabled: bool = True


class ConfigManager:
    """
    Loads, validates, and provides typed access to GhostBackup configuration.
    Secrets (SMTP password, encryption key) are always read from env vars only.
    """

    def __init__(self, config_path: Path = CONFIG_PATH):
        self._path = config_path
        self._data: dict = deepcopy(DEFAULTS)
        self._manifest_ref = None
        self._load()
        logger.info(f"Config loaded from {self._path}")

    def set_manifest(self, manifest) -> None:
        """Inject ManifestDB reference so config changes are logged to the audit trail."""
        self._manifest_ref = manifest

    # ── Load / save ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            _deep_merge(self._data, user_cfg)
        else:
            logger.warning(f"Config not found at {self._path} — using defaults")
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._save()

    def _save(self) -> None:
        safe = deepcopy(self._data)
        safe.pop("_secrets", None)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(safe, f, default_flow_style=False, allow_unicode=True)

    # ── Secrets (env vars only, never persisted) ──────────────────────────────

    @property
    def smtp_password(self) -> str:
        return os.getenv("GHOSTBACKUP_SMTP_PASSWORD", "")

    @property
    def encryption_key(self) -> Optional[bytes]:
        """
        Encryption key loaded from GHOSTBACKUP_ENCRYPTION_KEY environment variable.
        Returns bytes if set, None otherwise. Never read from config.yaml.
        """
        raw = os.getenv("GHOSTBACKUP_ENCRYPTION_KEY", "")
        return raw.encode() if raw else None

    @property
    def hkdf_salt(self) -> bytes:
        """
        Per-installation HKDF salt loaded from GHOSTBACKUP_HKDF_SALT environment variable.
        Falls back to the legacy hardcoded salt for backward compatibility with existing
        encrypted backups. Set this on new installations for stronger key isolation.
        """
        raw = os.getenv("GHOSTBACKUP_HKDF_SALT", "")
        if raw:
            return raw.encode()
        return b"ghostbackup-stream-v1"

    # ── SSD ───────────────────────────────────────────────────────────────────

    @property
    def ssd_path(self) -> str:
        return self._data.get("ssd_path", "")

    @property
    def ssd_path_obj(self) -> Optional[Path]:
        p = self.ssd_path
        return Path(p) if p else None

    @property
    def secondary_ssd_path(self) -> str:
        return self._data.get("secondary_ssd_path", "")

    # ── Encryption ────────────────────────────────────────────────────────────

    @property
    def encryption_config_enabled(self) -> bool:
        """True when encryption is enabled in config (regardless of whether key is set)."""
        return self._data.get("encryption", {}).get("enabled", True)

    @property
    def encryption_enabled(self) -> bool:
        """True only when encryption is enabled in config AND the key is set."""
        return bool(self.encryption_config_enabled and self.encryption_key)

    # ── Sources ───────────────────────────────────────────────────────────────

    @property
    def sources(self) -> list[SourceConfig]:
        return [SourceConfig(**s) for s in self._data.get("sources", [])]

    def get_enabled_sources(self) -> list[dict]:
        return [s for s in self._data.get("sources", []) if s.get("enabled", True)]

    def add_site(self, source: dict) -> dict:
        label = source.get("label") or source.get("name", "")
        path  = source.get("path", "")
        if not label:
            raise ValueError("Source requires a label")
        if not path:
            raise ValueError("Source requires a path")
        existing = [s.get("label") or s.get("name") for s in self._data["sources"]]
        if label in existing:
            raise ValueError(f"Source '{label}' already exists")
        created = {
            "label":   label,
            "path":    path,
            "enabled": source.get("enabled", True),
        }
        self._data["sources"].append(created)
        self._save()
        if self._manifest_ref:
            self._manifest_ref.log_config_change("sources.add", None, created)
        return created

    def remove_site(self, name: str) -> bool:
        for idx, source in enumerate(self._data["sources"]):
            source_name = source.get("label") or source.get("name")
            if source_name != name:
                continue

            removed = deepcopy(source)
            del self._data["sources"][idx]
            self._save()
            if self._manifest_ref:
                self._manifest_ref.log_config_change("sources.remove", removed, None)
            return True
        return False

    def update_site(self, name: str, updates: dict) -> dict:
        for source in self._data["sources"]:
            source_name = source.get("label") or source.get("name")
            if source_name != name:
                continue

            old = deepcopy(source)
            if "enabled" in updates:
                source["enabled"] = bool(updates["enabled"])

            self._save()
            if self._manifest_ref and old != source:
                self._manifest_ref.log_config_change("sources.update", old, source)
            return source
        raise ValueError(f"Source '{name}' not found")

    # ── Schedule ──────────────────────────────────────────────────────────────

    @property
    def schedule_time(self) -> str:
        return self._data["schedule"]["time"]

    @property
    def timezone(self) -> str:
        return self._data["schedule"]["timezone"]

    @property
    def max_job_minutes(self) -> int:
        return self._data["schedule"]["max_job_minutes"]

    @property
    def retry_count(self) -> int:
        return self._data["schedule"]["retry_count"]

    @property
    def retry_delay_minutes(self) -> int:
        return self._data["schedule"]["retry_delay_minutes"]

    # ── Performance ───────────────────────────────────────────────────────────

    @property
    def concurrency(self) -> int:
        return self._data["performance"]["concurrency"]

    @property
    def max_file_size_bytes(self) -> int:
        return self._data["performance"]["max_file_size_gb"] * 1024 ** 3

    @property
    def chunk_size_bytes(self) -> int:
        return self._data["performance"]["chunk_size_mb"] * 1024 * 1024

    # ── Backup ────────────────────────────────────────────────────────────────

    @property
    def verify_checksums(self) -> bool:
        return self._data["backup"].get("verify_checksums", True)

    @property
    def version_count(self) -> int:
        return self._data["backup"]["version_count"]

    @property
    def exclude_patterns(self) -> list[str]:
        return self._data["backup"]["exclude_patterns"]

    @property
    def circuit_breaker_threshold(self) -> float:
        return self._data.get("circuit_breaker_threshold", 0.05)

    # ── Watcher ───────────────────────────────────────────────────────────────

    @property
    def watcher_debounce_seconds(self) -> int:
        return self._data["watcher"]["debounce_seconds"]

    @property
    def watcher_cooldown_seconds(self) -> int:
        return self._data["watcher"]["cooldown_seconds"]

    # ── Retention ─────────────────────────────────────────────────────────────

    @property
    def retention_daily_days(self) -> int:
        return self._data["retention"]["daily_days"]

    @property
    def retention_weekly_days(self) -> int:
        return self._data["retention"]["weekly_days"]

    @property
    def retention_guard_days(self) -> int:
        return max(7, self._data["retention"]["guard_days"])

    @property
    def compliance_years(self) -> int:
        return self._data["retention"].get("compliance_years", 7)

    @property
    def compliance_min_days(self) -> int:
        return self.compliance_years * 365

    # ── SMTP ──────────────────────────────────────────────────────────────────

    @property
    def smtp_host(self) -> str:
        return self._data["smtp"]["host"]

    @property
    def smtp_port(self) -> int:
        return self._data["smtp"]["port"]

    @property
    def smtp_use_tls(self) -> bool:
        return self._data["smtp"]["use_tls"]

    @property
    def smtp_user(self) -> str:
        return self._data["smtp"].get("user", "")

    @property
    def smtp_recipients(self) -> list[str]:
        return self._data["smtp"]["recipients"]

    # ── Updates ───────────────────────────────────────────────────────────────

    def reset_to_defaults(self) -> None:
        """Reset all configuration to factory defaults and persist to disk."""
        self._data = deepcopy(DEFAULTS)
        self._save()
        logger.info("Configuration reset to factory defaults")

    def _validate_update(self, updates: dict) -> None:
        """Raise ValueError if any value in a flat update dict is out of range or invalid."""
        if "schedule_time" in updates:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(updates["schedule_time"])):
                raise ValueError("schedule_time must be HH:MM (00:00–23:59)")
        if "timezone" in updates:
            if updates["timezone"] not in available_timezones():
                raise ValueError(f"Unknown timezone: {updates['timezone']}")
        if "concurrency" in updates:
            v = updates["concurrency"]
            if not isinstance(v, int) or not (1 <= v <= 32):
                raise ValueError("concurrency must be an integer between 1 and 32")
        if "max_file_size_gb" in updates:
            v = updates["max_file_size_gb"]
            if not isinstance(v, int) or not (1 <= v <= 100):
                raise ValueError("max_file_size_gb must be an integer between 1 and 100")
        if "circuit_breaker_threshold" in updates:
            v = updates["circuit_breaker_threshold"]
            if not isinstance(v, (int, float)) or not (0.0 <= v <= 1.0):
                raise ValueError("circuit_breaker_threshold must be a float between 0.0 and 1.0")
        if "exclude_patterns" in updates:
            if not isinstance(updates["exclude_patterns"], list) or not all(
                isinstance(p, str) for p in updates["exclude_patterns"]
            ):
                raise ValueError("exclude_patterns must be a list of strings")

    def update(self, updates: dict) -> None:
        """
        Apply a flat update dict and log each changed field to the audit trail.
        Unknown keys are silently ignored.
        """
        self._validate_update(updates)
        mapping = {
            "ssd_path":                  ("ssd_path",),
            "secondary_ssd_path":        ("secondary_ssd_path",),
            "schedule_time":             ("schedule",    "time"),
            "timezone":                  ("schedule",    "timezone"),
            "concurrency":               ("performance", "concurrency"),
            "max_file_size_gb":          ("performance", "max_file_size_gb"),
            "verify_checksums":          ("backup",      "verify_checksums"),
            # version_count is stored in config but not yet enforced by the pruner.
            # It is intentionally excluded here so the API cannot write a value
            # that would silently have no effect.
            "exclude_patterns":          ("backup",      "exclude_patterns"),
            "circuit_breaker_threshold": ("circuit_breaker_threshold",),
        }
        ignored = []
        for key, val in updates.items():
            if key not in mapping:
                ignored.append(key)
                continue
            path = mapping[key]
            if len(path) == 1:
                old_val = self._data.get(path[0])
                self._data[path[0]] = val
            else:
                old_val = self._data.get(path[0], {}).get(path[1])
                self._data[path[0]][path[1]] = val
            if self._manifest_ref and old_val != val:
                self._manifest_ref.log_config_change(key, old_val, val)
        self._save()
        logger.info(f"Config updated: {list(updates.keys())}")
        return ignored

    def update_smtp(self, smtp: dict) -> None:
        SMTP_KEYS = {"host", "port", "sender", "recipients", "use_tls", "username", "user"}
        smtp_safe = {k: v for k, v in smtp.items() if k in SMTP_KEYS}
        _deep_merge(self._data["smtp"], smtp_safe)
        self._save()

    def update_retention(self, retention: dict) -> None:
        """
        Update retention settings, enforcing the compliance minimum (UK Companies Act 2006).
        Raises ValueError if the new values violate compliance or logical constraints.
        """
        new_guard  = retention.get("guard_days",  self.retention_guard_days)
        new_daily  = retention.get("daily_days",  self.retention_daily_days)
        new_weekly = retention.get("weekly_days", self.retention_weekly_days)

        if new_guard < 7:
            raise ValueError("guard_days cannot be less than 7")
        if new_weekly < self.compliance_min_days:
            raise ValueError(
                f"weekly_days ({new_weekly}) cannot be less than the compliance minimum "
                f"of {self.compliance_min_days} days ({self.compliance_years} years, "
                f"UK Companies Act 2006). Update compliance_years in config.yaml to change this."
            )
        if new_daily > new_weekly:
            raise ValueError("daily_days cannot exceed weekly_days")

        old = {
            "daily_days":  self.retention_daily_days,
            "weekly_days": self.retention_weekly_days,
            "guard_days":  self.retention_guard_days,
        }
        _deep_merge(self._data["retention"], {
            "daily_days":  new_daily,
            "weekly_days": new_weekly,
            "guard_days":  new_guard,
        })
        self._save()
        if self._manifest_ref:
            self._manifest_ref.log_config_change("retention", old, self._data["retention"])

    # ── Safe export ───────────────────────────────────────────────────────────

    def to_dict_safe(self) -> dict:
        """Return config dict safe for API responses — no secrets, computed fields added."""
        safe = deepcopy(self._data)
        safe.pop("_secrets", None)
        if "smtp" in safe:
            safe["smtp"].pop("password", None)
        safe["encryption_active"]   = self.encryption_enabled
        safe["compliance_min_days"] = self.compliance_min_days
        return safe

    # ── Logging ───────────────────────────────────────────────────────────────

    @property
    def log_level(self) -> str:
        return self._data["logging"]["level"]

    @property
    def log_retention_days(self) -> int:
        return self._data["logging"]["retention_days"]

    @property
    def log_dir(self) -> Path:
        return Path(self._data["logging"]["log_dir"])


# ── Module-level utilities ────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base in place."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
