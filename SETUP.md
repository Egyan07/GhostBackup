# GhostBackup — Setup Guide

Complete setup from scratch on the dedicated backup laptop.

## Prerequisites

- Windows 10 or 11
- Python 3.10 or later — [python.org](https://www.python.org/downloads/) *(tick "Add Python to PATH" during install)*
- Node.js 18 or later — [nodejs.org](https://nodejs.org/)

Verify both are installed before proceeding:

```
python --version
node --version
```

---

## Option A — Automated Setup (Recommended)

### Step 1 — Clone the repository

```
git clone https://github.com/Egyan07/GhostBackup.git
cd GhostBackup
```

### Step 2 — Run the installer

Double-click **`install.bat`** or run it from the terminal:

```
install.bat
```

The installer will:
1. Verify Python 3.10+ and Node.js 18+ are present
2. Create a Python virtual environment (`.venv`)
3. Install all Python packages from `backend/requirements.txt`
4. Install all Node packages via `npm install --legacy-peer-deps`
5. Ask you for:
   - The **source folder** to back up (your SharePoint-synced folder)
   - The **primary SSD drive path** (e.g. `D:\GhostBackup`)
   - An optional **secondary SSD path** for 3-2-1 redundancy
6. Generate an AES-256-GCM encryption key and save it to `.env.local`
7. Patch `backend/config/config.yaml` with your paths
8. Create `start.bat` as a one-click launcher

### Step 3 — Save the encryption key

After setup completes, the installer prints your encryption key on screen. **Copy it immediately and store it on a separate device** (phone, personal password manager, USB).

> If this key is lost, your backups cannot be decrypted. There is no recovery option.

> **Important:** GhostBackup will **refuse to start** if encryption is enabled (the default) but the key is missing or invalid. This is intentional — it prevents accidental unencrypted backups of sensitive data. If you see a startup error about encryption, verify that `GHOSTBACKUP_ENCRYPTION_KEY` is set correctly in `.env.local`.

### Step 4 — Configure email alerts (optional)

Open `backend\config\config.yaml` and fill in the `smtp` block:

```yaml
smtp:
  host: smtp.office365.com
  port: 587
  user: backup@redparrot.co.uk
  recipients:
    - it@redparrot.co.uk
```

Then add your Office 365 app password to `.env.local`:

```
GHOSTBACKUP_SMTP_PASSWORD=your-app-password-here
```

### Step 5 — Launch

Double-click **`start.bat`**, or run:

```
start.bat
```

> **Note:** `start.bat` runs `npm run dev` which starts the Vite development server alongside Electron. This is the normal way to run GhostBackup from a source install.

---

## Option B — Manual Setup

Use this if you prefer full control or are setting up on a non-standard environment.

### Step 1 — Clone

```
git clone https://github.com/Egyan07/GhostBackup.git
cd GhostBackup
```

### Step 2 — Python environment

```
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

### Step 3 — Generate encryption key

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Note:** This generates a key in the Fernet-compatible format (URL-safe base64) used by GhostBackup's encryption system. The actual backup encryption uses AES-256-GCM, but the key format remains Fernet-compatible for consistency.

**Store this key on a separate device. Loss of key = loss of access to all backups.**

### Step 4 — Create `.env.local`

Create a file named `.env.local` in the project root:

```
GHOSTBACKUP_ENCRYPTION_KEY=<paste your key here>
GHOSTBACKUP_HKDF_SALT=<generate with: python -c "import os; print(os.urandom(16).hex())">
GHOSTBACKUP_SMTP_PASSWORD=<your Office 365 app password>
```

`GHOSTBACKUP_HKDF_SALT` is a per-installation random value that strengthens encryption key derivation. Generate it once and store alongside your encryption key. If omitted, a static default is used (backward compatible but less secure).

This file is excluded from version control. Never commit it.

### Step 5 — Configure backup sources

```
copy backend\config\config.yaml.example backend\config\config.yaml
```

Open `backend\config\config.yaml` and set at minimum:

```yaml
ssd_path: "E:\\"

sources:
  - label: Accounts
    path: "C:\\Users\\YourName\\SharePoint\\Red Parrot\\Accounts"
    enabled: true
```

### Step 6 — Node dependencies

```
npm install --legacy-peer-deps
```

### Step 7 — Launch

```
npm run dev
```

---

## Step 8 — Verify the setup

Applies to both Option A and B:

1. Open the app — the dashboard should show **Encryption: Active**
2. Go to **Settings → SMTP → Send Test Email** and confirm receipt
3. Click **Run Backup Now** and verify files appear on the SSD
4. Go to **Settings → Verify Integrity** after the first run

---

## Running Tests

**Python backend:**

```
.venv\Scripts\activate
pytest backend/tests/ -v
```

**JavaScript frontend:**

```
npm test
```

---

## Monthly Maintenance Checklist

- [ ] Run **Verify Integrity** from Settings — confirm 0 corrupt, 0 missing
- [ ] Check that email alerts are still arriving
- [ ] Confirm the daily SSD rotation routine is being followed
- [ ] Review SSD free space — prune old backups from Settings if needed

---

## Error Code Reference

When the API returns an error, the response body contains a structured object with `code`, `message`, and `fix` fields. Use the table below to look up solutions.

| Code | Meaning | Fix |
|---------|-------------------------------------------|--------------------------------------------------------------------|
| GB-E001 | Encryption key not set | Set GHOSTBACKUP_ENCRYPTION_KEY via Settings or .env.local |
| GB-E002 | Encryption initialization failed | Verify the key is a valid Fernet key (base64-encoded, 44 chars) |
| GB-E003 | Key fingerprint mismatch on restore | The file was encrypted with a different key. Provide the original key. |
| GB-E010 | Primary SSD not connected | Connect the backup drive and verify the path in Settings |
| GB-E011 | SSD free space critically low | Prune old backups or connect a larger drive |
| GB-E020 | Backup already in progress | Wait for the current run to finish or stop it from the dashboard |
| GB-E021 | Source folder not found | Verify the source path exists and is accessible |
| GB-E022 | Circuit breaker triggered | Too many file failures in one library. Check file permissions. |
| GB-E023 | Backup job timed out | Increase max_job_minutes in config or reduce source size |
| GB-E030 | Invalid configuration value | Check field constraints in Settings or SETUP.md |
| GB-E031 | Retention below compliance minimum | weekly_days cannot be less than compliance_years x 365 |
| GB-E032 | Cannot delete immutable backup | Backups within the immutable window cannot be pruned |
| GB-E040 | Restore from failed run rejected | Select a successful or partial run instead |
| GB-E041 | No files found for restore | The selected run has no transferable files matching your criteria |
| GB-E042 | Path traversal blocked | The destination path attempted to escape the target directory |
| GB-E050 | SMTP test failed | Verify host, port, credentials, and TLS settings in Settings |
| GB-E060 | Cannot verify during backup | Wait for the backup to finish before running verification |
| GB-E061 | Cannot prune during backup | Wait for the backup to finish before pruning |

---

## Generating a New Encryption Key (Key Rotation)

### Option A — Via the Settings UI (recommended)

1. Run a **full backup** with the current key first (Settings → Run Full Backup Now)
2. Go to **Settings → Encryption → Generate New Key**
3. A confirmation modal appears showing the new key — click **Copy Key** and save it to a separate device before continuing
4. Click **I have saved the key — Activate** to confirm
5. Open `.env.local` in the project root and replace the value of `GHOSTBACKUP_ENCRYPTION_KEY` with the new key
6. Restart the app — all future backups will use the new key

### Option B — Manual (CLI)

1. Run a **full backup** with the current key first
2. Generate a new key:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   > **Note:** This generates a key in the Fernet-compatible format (URL-safe base64) used by GhostBackup's encryption system. The actual backup encryption uses AES-256-GCM, but the key format remains Fernet-compatible for consistency.
3. Update `GHOSTBACKUP_ENCRYPTION_KEY` in `.env.local`
4. Restart the app and run another full backup
5. Update your stored copy in the password manager

> Existing backups on the SSD remain encrypted with the old key — they are still valid and restorable as long as you keep the old key archived. Only new backups after the restart use the new key. Archive the old key separately if you need access to historical backups.
