"""
config.py — GhostBackup Configuration Manager  (Phase 2: Local SSD)

Replaces all cloud/Azure/Graph fields with:
  ssd_path         — absolute path to backup destination on the SSD
  sources          — list of local source folders (replaces cloud sites/libraries)
  verify_checksums — xxhash round-trip integrity check after every copy
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
    "ssd_path": "",                 # Set via UI — e.g. "D:\\GhostBackup"

    "schedule": {
        "time":                "08:00",
        "timezone":            "Asia/Kathmandu",
        "max_job_minutes":     240,
        "retry_count":         3,
        "retry_delay_minutes": 30,
    },

    "performance": {
        "concurrency":     4,        # parallel copy threads (ThreadPoolExecutor)
        "max_file_size_gb": 5,       # skip files larger than this
        "chunk_size_mb":   4,        # read/write chunk for large files + progress
    },

    "backup": {
        "verify_checksums": True,    # xxhash round-trip verify after each copy
        "version_count":    5,       # versioned copies to keep per file
        "exclude_patterns": [
            "~$*", "*.tmp", "Thumbs.db", ".DS_Store",
            "desktop.ini", "*.lnk", "pagefile.sys", "hiberfil.sys",
            "node_modules", ".git", "__pycache__", "*.pyc",
            ".venv", "venv", ".env",
        ],
    },

    "retention": {
        "daily_days":   90,
        "weekly_days":  365,
        "guard_days":   7,           # NEVER prune backups newer than this many days
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

    "sources": [],                   # list of SourceConfig dicts
}


class SourceConfig(BaseModel):
    """One local folder to back up to the SSD."""
    label:   str                                              # Display name
    path:    str                                              # Absolute local path
    enabled: bool = True
    circuit_breaker_threshold: float = Field(default=0.20, ge=0.05, le=1.0)


class ConfigManager:
    """
    Loads, validates, and provides typed access to GhostBackup configuration.
    The only secret is the optional SMTP password — always from env var,
    never written to config.yaml.
    """

    def __init__(self, config_path: Path = CONFIG_PATH):
        self._path = config_path
        self._data: dict = deepcopy(DEFAULTS)
        self._load()
        logger.info(f"Config loaded from {self._path}")

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

    # ── Secrets ───────────────────────────────────────────────────────────────

    @property
    def smtp_password(self) -> str:
        return os.getenv("GHOSTBACKUP_SMTP_PASSWORD", "")

    # ── SSD ───────────────────────────────────────────────────────────────────

    @property
    def ssd_path(self) -> str:
        return self._data.get("ssd_path", "")

    @property
    def ssd_path_obj(self) -> Optional[Path]:
        p = self.ssd_path
        return Path(p) if p else None

    # ── Sources ───────────────────────────────────────────────────────────────

    @property
    def sources(self) -> list[SourceConfig]:
        return [SourceConfig(**s) for s in self._data.get("sources", [])]

    def get_enabled_sources(self) -> list[dict]:
        return [s for s in self._data.get("sources", []) if s.get("enabled", True)]

    def add_site(self, source: dict) -> None:
        """UI calls this as add_site — maps to sources list. Accepts label or name."""
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

    def remove_site(self, name: str) -> bool:
        before = len(self._data["sources"])
        self._data["sources"] = [
            s for s in self._data["sources"]
            if (s.get("label") or s.get("name")) != name
        ]
        changed = len(self._data["sources"]) < before
        if changed:
            self._save()
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
        """Merge flat update dict from the API PATCH /config endpoint."""
        mapping = {
            "ssd_path":         ("ssd_path",),
            "schedule_time":    ("schedule",     "time"),
            "timezone":         ("schedule",     "timezone"),
            "concurrency":      ("performance",  "concurrency"),
            "max_file_size_gb": ("performance",  "max_file_size_gb"),
            "verify_checksums": ("backup",       "verify_checksums"),
            "version_count":    ("backup",       "version_count"),
            "exclude_patterns": ("backup",       "exclude_patterns"),
        }
        for key, val in updates.items():
            if key not in mapping:
                continue
            path = mapping[key]
            if len(path) == 1:          # top-level key
                self._data[path[0]] = val
            else:
                self._data[path[0]][path[1]] = val
        self._save()
        logger.info(f"Config updated: {list(updates.keys())}")

    def update_smtp(self, smtp: dict) -> None:
        smtp.pop("password", None)      # password lives in env only
        self._deep_merge(self._data["smtp"], smtp)
        self._save()

    def update_retention(self, retention: dict) -> None:
        if retention.get("guard_days", 7) < 7:
            raise ValueError("guard_days cannot be less than 7")
        self._deep_merge(self._data["retention"], {
            "daily_days":  retention.get("daily_days",  self.retention_daily_days),
            "weekly_days": retention.get("weekly_days", self.retention_weekly_days),
            "guard_days":  retention.get("guard_days",  self.retention_guard_days),
        })
        self._save()

    # ── Safe export ───────────────────────────────────────────────────────────

    def to_dict_safe(self) -> dict:
        safe = deepcopy(self._data)
        safe.pop("_secrets", None)
        if "smtp" in safe:
            safe["smtp"].pop("password", None)
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
