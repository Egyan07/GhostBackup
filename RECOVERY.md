# GhostBackup — Disaster Recovery Guide

This guide covers recovery procedures for common failure scenarios.
Keep a printed copy alongside your offsite backup drive.

---

## 1. Lost Encryption Key

**Symptom:** Restore fails with "Fernet decryption not initialised" or "Invalid token".

**Recovery steps:**

1. **Check Windows Credential Manager** (if key_storage = "keyring"):
   - Open Control Panel > Credential Manager > Windows Credentials
   - Look for `GhostBackup_encryption_key`
   - If present, copy the value to `.env.local` as `GHOSTBACKUP_ENCRYPTION_KEY=<value>`

2. **Check `.env.local`** (if key_storage = "env"):
   - File location: `<GhostBackup install dir>/.env.local`
   - Open in a text editor; the key is on the `GHOSTBACKUP_ENCRYPTION_KEY=` line

3. **Check environment variables:**
   - Open PowerShell: `[Environment]::GetEnvironmentVariable('GHOSTBACKUP_ENCRYPTION_KEY', 'User')`

4. **If the key is truly lost:**
   - Encrypted backups **cannot** be recovered without the original key
   - Any unencrypted source files still on disk are unaffected
   - Future backups will use a new key — old backups remain inaccessible
   - **Prevention:** Store the key in a password manager (1Password, Bitwarden) and print a paper backup

**Key format:** A 44-character base64 string (Fernet key), e.g. `dGhpcyBpcyBhIHNhbXBsZSBrZXkgZm9yIGRvY3M=`

---

## 2. Corrupted Manifest Database

**Symptom:** API returns 500 errors, "database disk image is malformed", or run history is missing.

**Recovery steps:**

1. **Stop GhostBackup** (close the app or kill the Python process)

2. **Locate the database:**
   - Default: `<install dir>/data/ghostbackup.db`
   - Also check for WAL files: `ghostbackup.db-wal` and `ghostbackup.db-shm`

3. **Attempt SQLite repair:**
   ```powershell
   sqlite3 ghostbackup.db ".recover" | sqlite3 ghostbackup_recovered.db
   ```

4. **If repair fails, rebuild from SSD:**
   - Rename the corrupt DB: `ren ghostbackup.db ghostbackup.db.corrupt`
   - Restart GhostBackup — it creates a fresh DB automatically
   - Run history will be lost, but your backup files on the SSD are intact
   - Run a full backup to re-index all files

5. **Restore WAL checkpoint (if DB looks empty but files exist):**
   ```powershell
   sqlite3 ghostbackup.db "PRAGMA wal_checkpoint(TRUNCATE);"
   ```

---

## 3. Deleted or Corrupted `.env.local`

**Symptom:** App starts but encryption is disabled, or API token authentication fails.

**Recovery steps:**

1. **Recreate the file** at `<install dir>/.env.local`:
   ```
   GHOSTBACKUP_ENCRYPTION_KEY=<your-key-here>
   ```

2. **If using keyring storage:** The encryption key is safe in Windows Credential Manager. Recreate `.env.local` with just the API token (auto-generated on next start).

3. **If the encryption key was only in `.env.local` and you don't have a backup:**
   - See "Lost Encryption Key" above
   - The API token regenerates automatically on restart

---

## 4. SSD Failure Mid-Backup

**Symptom:** Backup fails with "OS error", "Permission denied", or SSD disappears.

**Recovery steps:**

1. **Check if the SSD is still connected:**
   - Open File Explorer and verify the drive letter is visible
   - If not, try a different USB port or cable

2. **If the SSD has failed physically:**
   - Do NOT attempt to format or repair — this may destroy recoverable data
   - Your source files are safe (GhostBackup only reads from sources)
   - If you have a secondary SSD configured, your backups are on the secondary
   - Connect a new SSD, update the path in Settings, run a full backup

3. **Partial backup recovery:**
   - Files with `.ghosttmp` extension are incomplete — delete them
   - All other files on the SSD are complete (atomic rename ensures this)
   - The manifest DB knows which files were successfully backed up

4. **After replacing the SSD:**
   - Update `ssd_path` in Settings
   - Run a full backup (not incremental) to re-copy all files
   - Run verification after the backup completes

---

## 5. Application Won't Start

**Symptom:** Window doesn't appear, or shows a blank white screen.

**Recovery steps:**

1. **Check if the backend is running:**
   ```powershell
   netstat -ano | findstr 8765
   ```
   If port 8765 is in use by another process, kill it or change the port.

2. **Check logs:**
   - Electron logs: Check the terminal/console output
   - Backend logs: `<install dir>/logs/ghostbackup.log`

3. **Reset to defaults:**
   - Rename `config/config.yaml` to `config.yaml.bak`
   - Restart — the app creates a fresh config from defaults

4. **Reinstall without losing data:**
   - Your data is safe in: `data/ghostbackup.db`, `.env.local`, and the SSD
   - Reinstall GhostBackup, then restore these files to their original locations

---

## 6. Verification Finds Corrupted Files

**Symptom:** Verification reports "Hash mismatch" for one or more files.

**Recovery steps:**

1. **Identify the affected files** from the verification report

2. **Check if the source file is still intact:**
   - If yes: delete the corrupt backup from the SSD and run a new backup
   - If no: the backup is your only copy — attempt manual decryption to salvage what you can

3. **Check for SSD health issues:**
   - Run `chkdsk <drive>: /f` on the backup drive
   - Consider replacing the SSD if errors are found

4. **If corruption is widespread:**
   - The SSD may be failing — replace it immediately
   - Switch to your secondary SSD if configured
   - Run a full backup to the new drive

---

## Prevention Checklist

- [ ] Encryption key stored in a password manager
- [ ] Encryption key printed and stored securely (safe/lockbox)
- [ ] Secondary SSD configured for redundancy
- [ ] Weekly verification enabled in scheduler
- [ ] SMTP alerts configured for failure notifications
- [ ] Monthly restore drill to verify end-to-end recovery
- [ ] Offsite copy via OneDrive/Dropbox (see OFFSITE.md)
