"""
syncer.py — GhostBackup Local SSD Syncer

Handles file scanning, encrypted copying, restore, integrity verification,
and pruning of old backups. Supports an optional secondary SSD destination
for 3-2-1 redundancy.
"""

import fnmatch
import logging
import os
import shutil
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import psutil
import xxhash

from config import ConfigManager
from manifest import ManifestDB

logger = logging.getLogger("syncer")

WIN_PATH_PREFIX = "\\\\?\\"

# ── Streaming encryption constants ────────────────────────────────────────────
_STREAM_MAGIC = b"GBENC1"   # header identifying the streaming AES-GCM format
_ENCRYPTION_VERSION = b'\x01'  # version prefix for key rotation support
_NONCE_SIZE = 12             # AES-GCM standard nonce length
_LEN_SIZE = 4                # uint32 big-endian chunk ciphertext length


# ── Encryption helper ─────────────────────────────────────────────────────────

class _CryptoHelper:
    """
    AES-256-GCM streaming encryption/decryption for backup files.

    New backups are encrypted in fixed-size chunks so memory usage stays
    constant regardless of file size.  Legacy Fernet-encrypted files are
    detected automatically and decrypted transparently.
    """

    def __init__(self, key: Optional[bytes], salt: bytes = b"ghostbackup-stream-v1"):
        self._fernet = None
        self._aesgcm = None
        self._salt   = salt
        if key:
            try:
                import base64
                from cryptography.fernet import Fernet
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                from cryptography.hazmat.primitives.kdf.hkdf import HKDF

                # Keep Fernet instance for decrypting legacy backup files
                self._fernet = Fernet(key)

                # Derive a 256-bit AES key from the Fernet key material
                raw_key = base64.urlsafe_b64decode(key)
                derived = HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=self._salt,
                    info=b"aesgcm-encrypt",
                ).derive(raw_key)
                self._aesgcm = AESGCM(derived)

                logger.info("Backup encryption: ENABLED (AES-256-GCM streaming)")
            except Exception as e:
                logger.error(
                    f"Failed to initialise encryption: {e} — backups will be UNENCRYPTED"
                )
                self._fernet = None
                self._aesgcm = None

    @property
    def enabled(self) -> bool:
        return self._aesgcm is not None

    @property
    def key_fingerprint(self) -> Optional[str]:
        """First 16 hex chars of a SHA-256 hash of the derived AES key — never the key itself."""
        if self._aesgcm is None:
            return None
        import hashlib
        # _aesgcm._key is the raw 32-byte AES key stored by the AESGCM object
        try:
            raw = self._aesgcm._key
        except AttributeError:
            return None
        return hashlib.sha256(raw).hexdigest()[:16]

    @staticmethod
    def _is_stream_format(path: Path) -> bool:
        """Return True if the file starts with the streaming format header."""
        try:
            with open(path, "rb") as f:
                return f.read(len(_STREAM_MAGIC)) == _STREAM_MAGIC
        except OSError:
            return False

    # ── Encrypt (streaming, constant memory) ──────────────────────────────

    def encrypt_chunks(
        self,
        src_path: Path,
        dst_path: Path,
        chunk_bytes: int,
        on_progress: Optional[Callable] = None,
    ) -> None:
        """Encrypt *src_path* to *dst_path* using AES-256-GCM in fixed-size chunks."""
        with open(src_path, "rb") as fin, open(dst_path, "wb") as fout:
            fout.write(_STREAM_MAGIC)
            fout.write(_ENCRYPTION_VERSION)
            while True:
                plaintext = fin.read(chunk_bytes)
                if not plaintext:
                    fout.write(struct.pack(">I", 0))  # end-of-stream marker
                    break
                nonce = os.urandom(_NONCE_SIZE)
                ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
                fout.write(struct.pack(">I", len(ciphertext)))
                fout.write(nonce)
                fout.write(ciphertext)
                if on_progress:
                    on_progress(len(plaintext))

    # ── Decrypt (auto-detects streaming vs legacy Fernet) ─────────────────

    def decrypt_to(self, src_path: Path, dst_path: Path) -> None:
        """Decrypt a backup file to *dst_path*, auto-detecting format."""
        if self._is_stream_format(src_path):
            self._decrypt_stream(src_path, dst_path)
        else:
            # Legacy Fernet format — must load entire file
            dst_path.write_bytes(self._fernet.decrypt(src_path.read_bytes()))

    def _decrypt_stream(self, src_path: Path, dst_path: Path) -> None:
        with open(src_path, "rb") as fin, open(dst_path, "wb") as fout:
            magic = fin.read(len(_STREAM_MAGIC))
            if magic != _STREAM_MAGIC:
                raise ValueError("Invalid GhostBackup encrypted file header")
            version = fin.read(len(_ENCRYPTION_VERSION))
            if version != _ENCRYPTION_VERSION:
                raise ValueError(f"Unsupported encryption version: {version!r}")
            while True:
                hdr = fin.read(_LEN_SIZE)
                if len(hdr) < _LEN_SIZE:
                    raise ValueError("Truncated encrypted file")
                ct_len = struct.unpack(">I", hdr)[0]
                if ct_len == 0:
                    break
                nonce = fin.read(_NONCE_SIZE)
                if len(nonce) < _NONCE_SIZE:
                    raise ValueError("Truncated nonce in encrypted file")
                ciphertext = fin.read(ct_len)
                if len(ciphertext) < ct_len:
                    raise ValueError("Truncated chunk in encrypted file")
                fout.write(self._aesgcm.decrypt(nonce, ciphertext, None))

    # ── Streaming verify (decrypt + hash without buffering entire file) ───

    def decrypt_and_hash(self, path: Path) -> str:
        """Decrypt and return the xxHash of the plaintext (constant memory)."""
        h = xxhash.xxh64()
        if self._is_stream_format(path):
            with open(path, "rb") as fin:
                fin.read(len(_STREAM_MAGIC))  # skip header
                fin.read(len(_ENCRYPTION_VERSION))  # skip version byte
                while True:
                    hdr = fin.read(_LEN_SIZE)
                    if len(hdr) < _LEN_SIZE:
                        raise ValueError("Truncated encrypted file")
                    ct_len = struct.unpack(">I", hdr)[0]
                    if ct_len == 0:
                        break
                    nonce = fin.read(_NONCE_SIZE)
                    ciphertext = fin.read(ct_len)
                    h.update(self._aesgcm.decrypt(nonce, ciphertext, None))
        else:
            # Legacy Fernet — must load whole file (unavoidable for old backups)
            h.update(self._fernet.decrypt(path.read_bytes()))
        return h.hexdigest()

    def decrypt_bytes(self, data: bytes) -> bytes:
        """Decrypt in-memory Fernet token (legacy compatibility)."""
        return self._fernet.decrypt(data)


# ── SSD health ────────────────────────────────────────────────────────────────

def get_ssd_status(ssd_path: str) -> dict:
    if not ssd_path:
        return {"status": "not_configured", "error": "No SSD path set in config"}
    p = Path(ssd_path)
    try:
        if not p.exists():
            return {
                "status": "disconnected",
                "path":   ssd_path,
                "error":  "Path does not exist — drive may be unplugged",
            }
        usage   = shutil.disk_usage(ssd_path)
        used_gb = (usage.total - usage.free) / 1024 ** 3
        free_gb = usage.free  / 1024 ** 3
        tot_gb  = usage.total / 1024 ** 3
        fs_type = "unknown"
        try:
            for part in psutil.disk_partitions(all=True):
                try:
                    if Path(ssd_path).resolve().is_relative_to(Path(part.mountpoint).resolve()):
                        fs_type = part.fstype
                        break
                except (ValueError, TypeError):
                    continue
        except Exception:
            pass
        return {
            "status":       "ok",
            "path":         ssd_path,
            "used_gb":      round(used_gb, 2),
            "available_gb": round(free_gb, 2),
            "total_gb":     round(tot_gb,  2),
            "fs_type":      fs_type,
        }
    except PermissionError:
        return {
            "status": "disconnected",
            "path":   ssd_path,
            "error":  "Permission denied — cannot read drive",
        }
    except Exception as e:
        return {"status": "error", "path": ssd_path, "error": str(e)}


# ── File utilities ────────────────────────────────────────────────────────────

def _hash_file(path: Path, chunk_bytes: int = 65536) -> str:
    h = xxhash.xxh64()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _hash_bytes(data: bytes) -> str:
    return xxhash.xxh64(data).hexdigest()


def _extended_path(p: Path) -> str:
    s = str(p.resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return WIN_PATH_PREFIX + s
    return s


def _should_exclude(rel_path: str, patterns: list[str]) -> bool:
    p     = Path(rel_path)
    name  = p.name
    parts = p.parts
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
        if fnmatch.fnmatch(rel_path, pat):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


# ── Core syncer ───────────────────────────────────────────────────────────────

class LocalSyncer:

    def __init__(self, config: ConfigManager, manifest: ManifestDB):
        self._config   = config
        self._manifest = manifest
        self._crypto   = _CryptoHelper(config.encryption_key, salt=config.hkdf_salt)
        self._cleanup_orphan_tmp_files()
        if config.encryption_config_enabled and not self._crypto.enabled:
            logger.warning(
                "Encryption is enabled in config but GHOSTBACKUP_ENCRYPTION_KEY is not set. "
                "Backups will be stored UNENCRYPTED. Run SETUP.md step 3 to configure the key."
            )

    @property
    def encryption_active(self) -> bool:
        """True when encryption is initialised and ready."""
        return self._crypto.enabled

    @property
    def key_fingerprint(self) -> Optional[str]:
        """First 16 hex chars of SHA-256 of the derived AES key — safe to store, never the key."""
        return self._crypto.key_fingerprint

    def _cleanup_orphan_tmp_files(self) -> None:
        """Remove any .ghosttmp files left behind by a previous interrupted run."""
        ssd_path = self._config.ssd_path
        if not ssd_path or not Path(ssd_path).exists():
            return
        count = 0
        for tmp in Path(ssd_path).rglob("*.ghosttmp"):
            try:
                tmp.unlink()
                count += 1
            except OSError:
                pass
        if count:
            logger.info(f"Cleaned up {count} orphaned .ghosttmp file(s) from SSD")

    # ── Pre-flight ────────────────────────────────────────────────────────────

    def check_ssd(self) -> dict:
        return get_ssd_status(self._config.ssd_path)

    def hash_file(self, path) -> str:
        """Return the xxHash of a file at the given path."""
        return _hash_file(Path(path), self._config.chunk_size_bytes)

    def assert_ssd_ready(self) -> None:
        status = self.check_ssd()
        if status["status"] != "ok":
            raise RuntimeError(
                f"SSD not ready: {status.get('error', status['status'])}"
            )

    # ── Scan: detect changed files ────────────────────────────────────────────

    def scan_source(
        self,
        source: dict,
        force_full: bool = False,
    ) -> tuple[list[dict], int]:
        label    = source.get("label") or source.get("name", "?")
        src_path = Path(source["path"])

        if not src_path.exists():
            raise FileNotFoundError(f"Source folder not found: {src_path}")

        changed  = []
        skipped  = 0
        patterns = self._config.exclude_patterns
        max_size = self._config.max_file_size_bytes

        for entry in src_path.rglob("*"):
            if not entry.is_file():
                continue
            rel = str(entry.relative_to(src_path))
            if _should_exclude(rel, patterns):
                skipped += 1
                continue
            try:
                stat = entry.stat()
            except OSError:
                skipped += 1
                continue
            size  = stat.st_size
            mtime = stat.st_mtime
            if size > max_size:
                logger.warning(
                    f"Skipping oversized file ({size / (1024**3):.1f} GB): {rel}"
                )
                skipped += 1
                continue

            file_hash = None
            cached = None
            if not force_full:
                cached = self._manifest.get_file_hash(str(entry))
                if cached and abs(cached["mtime"] - mtime) < 0.001 and cached["size"] == size:
                    try:
                        file_hash = _hash_file(entry, self._config.chunk_size_bytes)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Cannot hash {rel}: {e}")
                        skipped += 1
                        continue

                    if cached["xxhash"] == file_hash:
                        skipped += 1
                        continue

            try:
                if file_hash is None:
                    file_hash = _hash_file(entry, self._config.chunk_size_bytes)
            except (OSError, PermissionError) as e:
                logger.warning(f"Cannot hash {rel}: {e}")
                skipped += 1
                continue

            # Content path: skip if hash matches even if mtime drifted
            if not force_full:
                cached = cached or self._manifest.get_file_hash(str(entry))
                if cached and cached["xxhash"] == file_hash:
                    self._manifest.save_file_hash(str(entry), file_hash, mtime, size)
                    skipped += 1
                    continue

            changed.append({
                "source_label":  label,
                "name":          entry.name,
                "original_path": str(entry),
                "rel_path":      rel,
                "size":          size,
                "mtime":         mtime,
                "xxhash":        file_hash,
            })

        logger.info(f"[{label}] Scan complete — {len(changed)} to copy, {skipped} skipped")
        return changed, skipped

    # ── Copy one file ─────────────────────────────────────────────────────────

    def copy_file(
        self,
        file_meta: dict,
        run_id: int,
        on_progress: Optional[Callable[[int], None]] = None,
        dest_root_override: Optional[Path] = None,
        _skip_secondary: bool = False,
    ) -> str:
        """
        Copy a single file to the SSD, encrypting if a key is configured.
        Writes to a .ghosttmp file first then atomically renames to prevent
        partial writes being mistaken for valid backups.
        Returns the final backup path as a string.
        """
        ssd_root = dest_root_override or Path(self._config.ssd_path)
        label    = file_meta["source_label"]
        rel_path = file_meta["rel_path"]
        src      = Path(file_meta["original_path"])
        dest     = ssd_root / _sanitise_label(label) / rel_path
        dest_tmp = dest.with_suffix(dest.suffix + ".ghosttmp")

        dest.parent.mkdir(parents=True, exist_ok=True)

        chunk = self._config.chunk_size_bytes
        try:
            if self._crypto.enabled:
                self._crypto.encrypt_chunks(
                    Path(_extended_path(src)), dest_tmp, chunk, on_progress
                )
            else:
                with open(_extended_path(src), "rb") as fsrc, \
                     open(_extended_path(dest_tmp), "wb") as fdst:
                    while True:
                        buf = fsrc.read(chunk)
                        if not buf:
                            break
                        fdst.write(buf)
                        if on_progress:
                            on_progress(len(buf))
        except PermissionError as e:
            dest_tmp.unlink(missing_ok=True)
            raise RuntimeError(f"File locked or permission denied: {src.name} — {e}")
        except OSError as e:
            dest_tmp.unlink(missing_ok=True)
            raise RuntimeError(f"OS error copying {src.name}: {e}")

        dest_tmp.replace(dest)

        if self._config.verify_checksums:
            if self._crypto.enabled:
                dest_hash = self._crypto.decrypt_and_hash(dest)
            else:
                dest_hash = _hash_file(dest, chunk)
            if dest_hash != file_meta["xxhash"]:
                dest.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Checksum mismatch after copy: {src.name} "
                    f"(src={file_meta['xxhash'][:8]}… dest={dest_hash[:8]}…)"
                )

        try:
            shutil.copystat(_extended_path(src), _extended_path(dest))
        except OSError:
            pass

        self._manifest.save_file_hash(
            file_meta["original_path"],
            file_meta["xxhash"],
            file_meta["mtime"],
            file_meta["size"],
        )

        if self._config.secondary_ssd_path and not _skip_secondary:
            try:
                self.copy_file(
                    file_meta, run_id,
                    on_progress=None,
                    dest_root_override=Path(self._config.secondary_ssd_path),
                    _skip_secondary=True,
                )
            except Exception as sec_err:
                logger.warning(f"Secondary SSD copy failed for {src.name}: {sec_err}")

        return str(dest)

    # ── Restore ───────────────────────────────────────────────────────────────

    def restore_files(
        self,
        files: list[dict],
        destination: str,
        on_progress: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        """Restore backed-up files to destination, decrypting if necessary."""
        dest_root = Path(destination).resolve()
        dest_root.mkdir(parents=True, exist_ok=True)

        restored = 0
        failed   = 0
        errors   = []
        chunk    = self._config.chunk_size_bytes

        for f in files:
            src           = Path(f.get("backup_path", ""))
            original_path = f.get("original_path", "")
            label         = f.get("source_label", "")

            rel_path = None
            if original_path:
                source_root = next(
                    (s.get("path", "") for s in self._config.get_enabled_sources()
                     if s.get("label") == label or s.get("name") == label),
                    None,
                )
                if source_root:
                    try:
                        rel_path = Path(original_path).relative_to(source_root)
                    except ValueError:
                        pass

            if not rel_path:
                rel_path = Path(f.get("name", src.name))

            dest = (dest_root / rel_path).resolve()
            if not str(dest).startswith(str(dest_root)):
                errors.append({"file": str(rel_path), "error": "Path traversal detected"})
                failed += 1
                continue

            if not src.exists():
                errors.append({"file": str(rel_path), "error": "Backup file not found on SSD"})
                failed += 1
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Warn if this file was encrypted with a different key than the current one
                file_fp = f.get("key_fingerprint")
                if file_fp and self._crypto.key_fingerprint and file_fp != self._crypto.key_fingerprint:
                    logger.warning(
                        f"Key fingerprint mismatch for {src.name}: "
                        f"file={file_fp}, current={self._crypto.key_fingerprint}. "
                        f"Restore may fail if the encryption key has been rotated."
                    )
                if self._crypto.enabled:
                    self._crypto.decrypt_to(src, dest)
                else:
                    with open(_extended_path(src), "rb") as fsrc, \
                         open(_extended_path(dest), "wb") as fdst:
                        while True:
                            buf = fsrc.read(chunk)
                            if not buf:
                                break
                            fdst.write(buf)
                            if on_progress:
                                on_progress(str(rel_path), len(buf))
                restored += 1
            except (PermissionError, OSError, RuntimeError) as e:
                errors.append({"file": str(rel_path), "error": str(e)})
                failed += 1

        return {"restored": restored, "failed": failed, "errors": errors}

    # ── Verification ──────────────────────────────────────────────────────────

    def verify_backups(self, source_label: Optional[str] = None) -> dict:
        """
        Re-reads backup files and verifies their hashes against the manifest.
        Recommended to run monthly to catch silent SSD corruption early.
        Returns {verified, failed, missing, errors}.
        """
        verified = 0
        failed   = 0
        missing  = 0
        errors   = []
        chunk    = self._config.chunk_size_bytes

        sources = (
            [s for s in self._config.get_enabled_sources()
             if (s.get("label") or s.get("name")) == source_label]
            if source_label else self._config.get_enabled_sources()
        )

        for source in sources:
            label = source.get("label") or source.get("name", "")
            rows  = self._manifest.get_latest_backed_up_files_for_source(label)

            seen_paths: set[str] = set()
            for row in rows:
                bp   = row["backup_path"]
                xh   = row["xxhash"]
                name = row["name"]
                if bp in seen_paths:
                    continue
                seen_paths.add(bp)

                bp_path = Path(bp)
                if not bp_path.exists():
                    missing += 1
                    errors.append({"file": name, "error": "Backup file missing from SSD"})
                    continue

                try:
                    if self._crypto.enabled:
                        actual_hash = self._crypto.decrypt_and_hash(bp_path)
                    else:
                        actual_hash = _hash_file(bp_path, chunk)

                    if actual_hash != xh:
                        failed += 1
                        errors.append({
                            "file":  name,
                            "error": (
                                f"Hash mismatch — backup may be corrupted "
                                f"(expected={xh[:8]}… got={actual_hash[:8]}…)"
                            ),
                        })
                    else:
                        verified += 1
                except (OSError, RuntimeError) as e:
                    failed += 1
                    errors.append({"file": name, "error": f"Verification error: {e}"})

        logger.info(
            f"Verification complete — {verified} OK, {failed} corrupt, {missing} missing"
        )
        return {
            "verified": verified,
            "failed":   failed,
            "missing":  missing,
            "errors":   errors[:50],
        }

    # ── Pruning ───────────────────────────────────────────────────────────────

    def prune_old_backups(
        self,
        daily_days: int,
        weekly_days: int,
        guard_days: int,
    ) -> int:
        guard_cutoff = datetime.now(timezone.utc) - timedelta(days=guard_days)
        daily_cutoff = datetime.now(timezone.utc) - timedelta(days=daily_days)
        removed      = 0

        for source in self._config.get_enabled_sources():
            label     = source.get("label") or source.get("name", "")
            old_files = self._manifest.get_backup_files_for_prune(
                label, daily_cutoff.isoformat()
            )
            pruned_dates: set[str] = set()
            for f in old_files:
                backed_up = datetime.fromisoformat(
                    f.get("started_at", datetime.now(timezone.utc).isoformat())
                )
                if backed_up > guard_cutoff:
                    continue
                bp = Path(f["backup_path"])
                if bp.exists():
                    try:
                        bp.unlink()
                        removed += 1
                        # Track the date so we can mark the run as pruned
                        pruned_dates.add(backed_up.strftime("%Y-%m-%d"))
                    except OSError as e:
                        logger.warning(f"Could not prune {bp}: {e}")

            # Mark runs pruned only when files were actually deleted
            for date_str in pruned_dates:
                next_day = (
                    datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y-%m-%d")
                self._manifest.mark_run_pruned(date_str, next_day)

        logger.info(f"Prune complete — {removed} files removed")
        return removed


# ── Utilities ─────────────────────────────────────────────────────────────────

def _sanitise_label(label: str) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ ")
    s = "".join(c if c in keep else "_" for c in label).strip(" _")
    return s or "source"
