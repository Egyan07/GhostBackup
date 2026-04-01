"""
errors.py — Structured error codes for GhostBackup API.
Each error has a code (GB-Exxx), a human-readable message, and a fix suggestion.
"""

from dataclasses import dataclass
from typing import Optional
from fastapi import HTTPException


@dataclass(frozen=True)
class GBError:
    code: str
    message: str
    fix: str = ""


ERRORS: dict[str, GBError] = {
    "GB-E001": GBError("GB-E001", "Encryption key not set", "Set GHOSTBACKUP_ENCRYPTION_KEY via Settings or .env.local"),
    "GB-E002": GBError("GB-E002", "Encryption initialization failed", "Verify the key is a valid Fernet key (base64-encoded, 44 chars)"),
    "GB-E003": GBError("GB-E003", "Key fingerprint mismatch on restore", "The file was encrypted with a different key. Provide the original key."),
    "GB-E010": GBError("GB-E010", "Primary SSD not connected", "Connect the backup drive and verify the path in Settings"),
    "GB-E011": GBError("GB-E011", "SSD free space critically low", "Prune old backups or connect a larger drive"),
    "GB-E020": GBError("GB-E020", "Backup already in progress", "Wait for the current run to finish or stop it from the dashboard"),
    "GB-E021": GBError("GB-E021", "Source folder not found", "Verify the source path exists and is accessible"),
    "GB-E022": GBError("GB-E022", "Circuit breaker triggered", "Too many file failures in one library. Check file permissions."),
    "GB-E023": GBError("GB-E023", "Backup job timed out", "Increase max_job_minutes in config or reduce source size"),
    "GB-E030": GBError("GB-E030", "Invalid configuration value", "Check field constraints in Settings or SETUP.md"),
    "GB-E031": GBError("GB-E031", "Retention below compliance minimum", "weekly_days cannot be less than compliance_years x 365"),
    "GB-E032": GBError("GB-E032", "Cannot delete immutable backup", "Backups within the immutable window cannot be pruned"),
    "GB-E040": GBError("GB-E040", "Restore from failed run rejected", "Select a successful or partial run instead"),
    "GB-E041": GBError("GB-E041", "No files found for restore", "The selected run has no transferable files matching your criteria"),
    "GB-E042": GBError("GB-E042", "Path traversal blocked", "The destination path attempted to escape the target directory"),
    "GB-E050": GBError("GB-E050", "SMTP test failed", "Verify host, port, credentials, and TLS settings in Settings"),
    "GB-E060": GBError("GB-E060", "Cannot verify during backup", "Wait for the backup to finish before running verification"),
    "GB-E061": GBError("GB-E061", "Cannot prune during backup", "Wait for the backup to finish before pruning"),
}


def raise_gb(code: str, status: int = 400, detail_override: Optional[str] = None) -> None:
    err = ERRORS[code]
    raise HTTPException(
        status_code=status,
        detail={
            "code": err.code,
            "message": detail_override or err.message,
            "fix": err.fix,
        },
    )
