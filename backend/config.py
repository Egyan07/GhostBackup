"""
config.py — GhostBackup Configuration Manager

Fixes applied:
  - Default timezone changed to Europe/London (UK accounting firm) [FIX]
  - compliance_years added (7 years, UK Companies Act 2006)        [FIX-P2]
  - retention guard enforces compliance_years minimum              [FIX-P2]
  - secondary_ssd_path added for 3-2-1 backup redundancy          [FIX-P3]
  - circuit_breaker_threshold default lowered to 0.05 (5%)        [FIX-P3]
  - update() logs changes to audit trail via optional manifest ref [FIX-P2]
  - encryption_enabled flag added (key via env var)               [FIX-P1]
"""

import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("config")

CONFIG_PATH = Path(os.getenv("GHOSTBACKUP_CONFIG", "config/config.yaml"))

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "ssd_path": "",
    "secondary_ssd_path": "",      # FIX-P3: second destination for 3-2-1 rule

    "encryption": {
        "enabled": True,           # FIX-P1: encrypt backup files at rest
        # Key stored in GHOSTBACKUP_ENCRYPTION_KEY env var — never in config
    },

    "schedule": {
        "time":                "08:00",
        "timezone":            "Europe/London",   # FIX: was Asia/Kathmandu
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

    # FIX-P2: Retention extended to meet UK Companies Act 2006 (7 years)
    "retention": {
        "daily_days":      365,    # 1 year daily (was 90 days — too short for compliance)
        "weekly_days":     2555,   # 7 years weekly
        "compliance_years": 7,     # FIX-P2: minimum legal retention (Companies Act 2006)
        "guard_days":      7,
    },

    "smtp": {
        "host":       "smtp.office365.com",
        "port":       587,
        "use_tls":    True,
        "recipients": [],
    },

    "logging": {
        "level":          "INFO",
        "retention_days": 365,
        "log_dir":        "logs",
    },

    "sources": [],

    # FIX-P3: Circuit breaker lowered to 5% for financial data sensitivity
    "circuit_breaker_threshold": 0.05,
}


class SourceConfig(BaseModel):
    label:   str
    path:    str
    enabled: bool = True
    circuit_breaker_threshold: float = Field(default=0.05, ge=0.01, le=1.0)


class ConfigManager:
    """
    Loads, validates, and provides typed access to GhostBackup configuration.
    Secrets (SMTP password, encryption key) are always read from env vars only.
    """

    def __init__(self, config_path: Path = CONFIG_PATH):
        self._path = config_path
        self._data: dict = deepcopy(DEFAULTS)
        self._manifest_ref = None   # injected by api.py for audit logging
        self._load()
        logger.info(f"Config loaded from {self._path}")

    def set_manifest(self, manifest) -> None:
        """Inject ManifestDB reference for audit trail logging."""
        self._manifest_ref = manifest

    # ── Load / save ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            self._deep_merge(self._data, user_cfg)
        else:
            logger.warning(f"Config not found at {self._path} — using defaults")
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._save()

    def _save(self) -> None:
        safe = deepcopy(self._data)
        safe.pop("_secrets", None)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(safe, f, default_flow_style=False, allow_unicode=True)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConfigManager._deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    # ── Secrets (env vars only, never persisted) ──────────────────────────────

    @property
    def smtp_password(self) -> str:
        return os.getenv("GHOSTBACKUP_SMTP_PASSWORD", "")

    @property
    def encryption_key(self) -> Optional[bytes]:
        """
        FIX-P1: Encryption key from env var only. Returns bytes or None.
        Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        """
        raw = os.getenv("GHOSTBACKUP_ENCRYPTION_KEY", "")
        return raw.encode() if raw else None

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
        """FIX-P3: Optional second backup destination for redundancy."""
        return self._data.get("secondary_ssd_path", "")

    # ── Encryption ────────────────────────────────────────────────────────────

    @property
    def encryption_enabled(self) -> bool:
        """FIX-P1: Encryption is active only if enabled in config AND key is set."""
        cfg_enabled = self._data.get("encryption", {}).get("enabled", True)
        return cfg_enabled and self.encryption_key is not None

    # ── Sources ───────────────────────────────────────────────────────────────

    @property
    def sources(self) -> list[SourceConfig]:
        return [SourceConfig(**s) for s in self._data.get("sources", [])]

    def get_enabled_sources(self) -> list[dict]:
        return [s for s in self._data.get("sources", []) if s.get("enabled", True)]

    def add_site(self, source: dict) -> None:
        label = source.get("label") or source.get("name", "")
        path  = source.get("path", "")
        if not label or not path:
            raise ValueError("Source requires both a label and a path")
        existing = [s.get("label") or s.get("name") for s in self._data["sources"]]
        if label in existing:
            raise ValueError(f"Source '{label}' already exists")
        self._data["sources"].append({
            "label":   label,
            "path":    path,
            "enabled": source.get("enabled", True),
        })
        self._save()
        if self._manifest_ref:
            self._manifest_ref.log_config_change("sources.add", None, {"label": label, "path": path})

    def remove_site(self, name: str) -> bool:
        before  = len(self._data["sources"])
        removed = next((s for s in self._data["sources"]
                        if (s.get("label") or s.get("name")) == name), None)
        self._data["sources"] = [
            s for s in self._data["sources"]
            if (s.get("label") or s.get("name")) != name
        ]
        changed = len(self._data["sources"]) < before
        if changed:
            self._save()
            if self._manifest_ref:
                self._manifest_ref.log_config_change("sources.remove", removed, None)
        return changed

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
        """FIX-P3: Default lowered to 5% for financial data sensitivity."""
        return self._data.get("circuit_breaker_threshold", 0.05)

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
        """FIX-P2: Minimum retention required by UK Companies Act 2006."""
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

    def update(self, updates: dict) -> None:
        """Merge flat update dict and log each change to the audit trail."""
        mapping = {
            "ssd_path":             ("ssd_path",),
            "secondary_ssd_path":   ("secondary_ssd_path",),
            "schedule_time":        ("schedule",     "time"),
            "timezone":             ("schedule",     "timezone"),
            "concurrency":          ("performance",  "concurrency"),
            "max_file_size_gb":     ("performance",  "max_file_size_gb"),
            "verify_checksums":     ("backup",       "verify_checksums"),
            "version_count":        ("backup",       "version_count"),
            "exclude_patterns":     ("backup",       "exclude_patterns"),
            "circuit_breaker_threshold": ("circuit_breaker_threshold",),
        }
        for key, val in updates.items():
            if key not in mapping:
                continue
            path = mapping[key]
            # Capture old value for audit
            if len(path) == 1:
                old_val = self._data.get(path[0])
                self._data[path[0]] = val
            else:
                old_val = self._data.get(path[0], {}).get(path[1])
                self._data[path[0]][path[1]] = val
            # FIX-P2: Log to audit trail
            if self._manifest_ref and old_val != val:
                self._manifest_ref.log_config_change(key, old_val, val)
        self._save()
        logger.info(f"Config updated: {list(updates.keys())}")

    def update_smtp(self, smtp: dict) -> None:
        smtp.pop("password", None)
        self._deep_merge(self._data["smtp"], smtp)
        self._save()

    def update_retention(self, retention: dict) -> None:
        """
        FIX-P2: Prevent setting retention below compliance minimum (7 years).
        """
        if retention.get("guard_days", 7) < 7:
            raise ValueError("guard_days cannot be less than 7")

        new_daily  = retention.get("daily_days",  self.retention_daily_days)
        new_weekly = retention.get("weekly_days", self.retention_weekly_days)
        min_days   = self.compliance_min_days

        if new_weekly < min_days:
            raise ValueError(
                f"weekly_days ({new_weekly}) cannot be less than the compliance minimum "
                f"of {min_days} days ({self.compliance_years} years, UK Companies Act 2006). "
                f"To change this, update compliance_years in config.yaml."
            )
        if new_daily > new_weekly:
            raise ValueError("daily_days cannot exceed weekly_days")

        old = {
            "daily_days":  self.retention_daily_days,
            "weekly_days": self.retention_weekly_days,
        }
        self._deep_merge(self._data["retention"], {
            "daily_days":  new_daily,
            "weekly_days": new_weekly,
            "guard_days":  retention.get("guard_days", self.retention_guard_days),
        })
        self._save()
        if self._manifest_ref:
            self._manifest_ref.log_config_change("retention", old, self._data["retention"])

    # ── Safe export ───────────────────────────────────────────────────────────

    def to_dict_safe(self) -> dict:
        safe = deepcopy(self._data)
        safe.pop("_secrets", None)
        if "smtp" in safe:
            safe["smtp"].pop("password", None)
        # Surface computed properties for UI
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
