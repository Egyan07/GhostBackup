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
4. Install all Node packages via `npm install`
5. Ask you for:
   - The **source folder** to back up (your SharePoint-synced folder)
   - The **primary SSD drive path** (e.g. `D:\GhostBackup`)
   - An optional **secondary SSD path** for 3-2-1 redundancy
6. Generate a Fernet encryption key and save it to `.env.local`
7. Patch `backend/config/config.yaml` with your paths
8. Create `start.bat` as a one-click launcher

### Step 3 — Save the encryption key

After setup completes, the installer prints your encryption key on screen. **Copy it immediately and store it on a separate device** (phone, personal password manager, USB).

> If this key is lost, your backups cannot be decrypted. There is no recovery option.

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

**Store this key on a separate device. Loss of key = loss of access to all backups.**

### Step 4 — Create `.env.local`

Create a file named `.env.local` in the project root:

```
GHOSTBACKUP_ENCRYPTION_KEY=<paste your key here>
GHOSTBACKUP_SMTP_PASSWORD=<your Office 365 app password>
```

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
npm install
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
3. Update `GHOSTBACKUP_ENCRYPTION_KEY` in `.env.local`
4. Restart the app and run another full backup
5. Update your stored copy in the password manager

> Existing backups on the SSD remain encrypted with the old key — they are still valid and restorable as long as you keep the old key archived. Only new backups after the restart use the new key. Archive the old key separately if you need access to historical backups.
