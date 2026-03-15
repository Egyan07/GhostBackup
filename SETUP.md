# GhostBackup — Setup Guide

Complete setup from zero to a running desktop app.  
No Azure account, no cloud credentials, no internet connection required.

---

## Prerequisites

| Requirement | Version | Download |
|---|---|---|
| Node.js | 18+ | https://nodejs.org |
| Python | 3.10+ | https://python.org |
| A backup drive | Any local SSD or HDD mounted as a drive letter | — |

---

## Step 1 — Install Python dependencies

```powershell
cd backend
pip install -r requirements.txt
```

This installs FastAPI, APScheduler, xxhash, psutil, and watchdog.  
No Microsoft or cloud packages are required.

---

## Step 2 — Install Node.js dependencies

```powershell
# From the project root
npm install
```

---

## Step 3 — Set credentials (optional)

The only credential GhostBackup needs is an SMTP password for email alerts.  
If you don't need email alerts, skip this step entirely.

Create `.env.local` in the project root (this file is gitignored):

```
GHOSTBACKUP_SMTP_PASSWORD="your-email-password"
```

Or set it as a Windows environment variable:

```powershell
$env:GHOSTBACKUP_SMTP_PASSWORD = "your-email-password"
```

---

## Step 4 — Run in development

```powershell
npm run dev
```

This starts both the React dev server (port 3000) and Electron simultaneously.  
The Python backend is spawned automatically by Electron on port 8765.

The app opens minimized to the system tray on first launch.  
Double-click the tray icon to open the UI.

---

## Step 5 — First-time configuration (in the UI)

1. **Backup Config → SSD Destination** — click Browse and select your backup drive folder (e.g. `D:\GhostBackup`)
2. **Backup Config → Source Folders** — click Add Folder and select each folder you want to back up
3. **Settings → Email Alerts** — enter your SMTP details and recipient addresses if you want failure emails
4. **Settings → Real-Time File Watcher** — click Start Watcher to enable automatic backup on file change

The daily scheduled backup runs at **08:00 NPT** automatically.  
The watcher triggers incremental backups within 15 seconds of a file change.

---

## Step 6 — Windows auto-start (optional)

Open the app → click the tray icon → **Settings → Start with Windows**.  
When enabled, GhostBackup launches silently at boot and stays in the tray.

---

## Step 7 — Build for production (Windows installer)

Before building, revert the dev hardcode in `electron/main.js`:

```js
// Change this line:
const IS_DEV = true;
// To:
const IS_DEV = process.env.NODE_ENV === "development";
```

Then build:

```powershell
npm run build:electron
```

Output: `release/GhostBackup Setup 1.0.0.exe`

---

## Project structure

```
GhostBackup/
├── electron/
│   ├── main.js          ← Electron main process (Phase 1+2: startup, tray, notify server)
│   └── preload.js       ← Secure contextBridge IPC to renderer
├── src/
│   ├── index.html       ← React entry HTML
│   ├── main.jsx         ← React entry point + backend loader
│   ├── GhostBackup.jsx  ← Full UI (6 screens)
│   └── api-client.js    ← All fetch() calls to FastAPI
├── backend/
│   ├── api.py           ← FastAPI server (port 8765) — job orchestration + all endpoints
│   ├── config.py        ← Config loader (ssd_path, sources, verify_checksums)
│   ├── syncer.py        ← Local filesystem engine (scan, copy, verify, restore, prune)
│   ├── watcher.py       ← Real-time file watcher (watchdog, debounce, cooldown)
│   ├── manifest.py      ← SQLite database (runs, files, file_hashes, logs)
│   ├── scheduler.py     ← APScheduler 08:00 cron + watchdog + retry
│   ├── reporter.py      ← Alert manager + SMTP email reports
│   └── requirements.txt
├── config/
│   └── config.yaml      ← App configuration (no secrets ever)
├── .env.local           ← SMTP password only (gitignored)
├── package.json
├── vite.config.js
├── README.md
└── SETUP.md
```

---

## Troubleshooting

**"Backend not found" on startup**  
→ Ensure Python 3.10+ is installed and `pip install -r backend/requirements.txt` was run

**Backup runs but no files are copied**  
→ Check that your source folder paths exist and the SSD path is set correctly in Backup Config

**SSD shows as "Unavailable" in the UI**  
→ Check the drive letter is mounted (open File Explorer). Click Refresh in Settings → SSD Health

**Watcher not triggering**  
→ Check Settings → Real-Time File Watcher — ensure it shows "● Watching". If sources were added after the watcher started, click Stop then Start to reload

**Email not sending**  
→ Use Settings → Send Test Email to debug. SMTP settings for Office 365:
```
Host: smtp.office365.com
Port: 587
TLS:  enabled
```

**Port 8765 already in use**  
→ GhostBackup kills this automatically on startup. If it fails, run:
```powershell
netstat -ano | findstr :8765
taskkill /PID <pid> /F
```
