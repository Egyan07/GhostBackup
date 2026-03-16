# GhostBackup — Setup Guide

## Prerequisites
- Python 3.10+
- Node.js 18+

## Step 1 — Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

## Step 2 — Create your config
```bash
cp backend/config/config.yaml.example backend/config/config.yaml
# Edit config.yaml — set ssd_path, sources, smtp settings
```

## Step 3 — Generate encryption key (REQUIRED for UK GDPR compliance)
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output and add to `.env.local`:
```
GHOSTBACKUP_ENCRYPTION_KEY="<paste key here>"
```
**Keep this key safe** — without it, encrypted backups cannot be restored.
Store a copy offline (e.g. printed in a secure physical location).

## Step 4 — Set SMTP password (optional)
Add to `.env.local`:
```
GHOSTBACKUP_SMTP_PASSWORD="your-smtp-app-password"
```

## Step 5 — Install Node dependencies and run
```bash
npm install
npm run dev          # Development mode
npm run build:electron   # Build installer
```

## Security Notes
- `.env.local` is gitignored — never commit it
- `backend/config/config.yaml` is gitignored — never commit it
- The API token is auto-generated on each launch — no configuration needed
- Backup files are AES-128-CBC encrypted at rest when key is set

## UK Compliance
Retention defaults meet UK Companies Act 2006 requirements (7-year minimum).
The compliance floor cannot be lowered via the UI — only by editing config.yaml directly.

## Backup Verification
Run periodic integrity checks from the Settings panel → "Verify Backups".
This re-reads and hash-verifies all backed-up files against the manifest.
Set up a monthly verification schedule for compliance evidence.
