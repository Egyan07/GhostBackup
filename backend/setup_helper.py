"""
setup_helper.py — Run once during installation (called by install.bat).

Generates an encryption key, asks for backup paths, writes .env.local,
and patches config.yaml with the user's source and destination paths.
"""

import ntpath
import shutil
import sys
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).parent.parent

    # ── Generate encryption key (skip if already configured) ──────────────
    env_path   = root / ".env.local"
    key        = None
    key_is_new = False

    if env_path.exists():
        # Re-running setup — preserve the existing key to avoid locking out old backups
        existing = env_path.read_text(encoding="utf-8")
        for line in existing.splitlines():
            if line.startswith("GHOSTBACKUP_ENCRYPTION_KEY="):
                key = line.split("=", 1)[1].strip()
                break

    salt        = None
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8")
        for line in existing.splitlines():
            if line.startswith("GHOSTBACKUP_HKDF_SALT="):
                salt = line.split("=", 1)[1].strip()
                break

    if not key:
        try:
            import os
            from cryptography.fernet import Fernet
            key  = Fernet.generate_key().decode()
            salt = os.urandom(16).hex()   # 16-byte random hex salt
            key_is_new = True
        except ImportError:
            print("[ERROR] cryptography package missing — run pip install -r backend/requirements.txt")
            return 1
    else:
        print("  [OK] Existing encryption key found in .env.local — preserving it.")
        print("       Delete .env.local manually if you intentionally want a new key.")
        print()

    # ── Ask for backup paths ───────────────────────────────────────────────
    print("  Where are the files you want to back up?")
    print("  This is usually the folder synced from SharePoint on this laptop.")
    print("  Example: C:\\Users\\admin\\RedParrot\\Clients")
    source_path = input("  Source path: ").strip()
    print()

    print("  Where is your primary backup SSD?")
    print("  Example: D:\\GhostBackup")
    ssd_path = input("  Primary SSD drive path: ").strip()
    print()

    print("  Secondary SSD path (press Enter to skip):")
    secondary_path = input("  Secondary SSD drive path: ").strip()
    print()

    # ── Write .env.local (only when a new key was generated) ──────────────
    if key_is_new:
        env_path.write_text(
            f"GHOSTBACKUP_ENCRYPTION_KEY={key}\n"
            f"GHOSTBACKUP_HKDF_SALT={salt}\n"
            f"GHOSTBACKUP_SMTP_PASSWORD=\n",
            encoding="utf-8",
        )

    # ── Copy and patch config.yaml ─────────────────────────────────────────
    example = root / "backend" / "config" / "config.yaml.example"
    config  = root / "backend" / "config" / "config.yaml"

    if not config.exists():
        shutil.copy2(str(example), str(config))

    with open(config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    if ssd_path:
        cfg["ssd_path"] = ssd_path

    if secondary_path:
        cfg["secondary_ssd_path"] = secondary_path

    if source_path:
        label = ntpath.basename(source_path) or "My Files"
        sources = cfg.get("sources") or []
        if not any(s.get("path") == source_path for s in sources):
            sources.append({"label": label, "path": source_path, "enabled": True})
        cfg["sources"] = sources

    with open(config, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    # ── Print key prominently (only when newly generated) ─────────────────
    border = "=" * 60
    if key_is_new:
        print()
        print(f"  {border}")
        print(f"  IMPORTANT — SAVE YOUR ENCRYPTION KEY")
        print(f"  {border}")
        print()
        print(f"  {key}")
        print()
        print(f"  {border}")
        print()
        print("  This key is also saved in .env.local in this folder.")
        print("  Store a copy on a SEPARATE device (phone, USB, cloud note).")
        print("  If you lose the key your backups CANNOT be decrypted.")
        print()
    print("  Summary")
    print(f"  -------")
    print(f"  Source path  : {source_path or '(not set — add later via Settings)'}")
    print(f"  Primary SSD  : {ssd_path or '(not set)'}")
    if secondary_path:
        print(f"  Secondary SSD: {secondary_path}")
    print()
    print("  To adjust settings later, edit: backend\\config\\config.yaml")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
