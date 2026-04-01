\# 🌍 Offsite Backup Guide



No configuration needed. Everything described here works with your existing GhostBackup setup — zero changes required.



\---



\## Why Offsite Matters



Your GhostBackup SSDs protect you from file corruption, accidental deletion, and hardware failure. But they don't protect you from:



\- Fire or flood — both drives are in the same building  

\- Theft — someone takes the machine and the SSDs  

\- Power surge — fries everything connected to the same circuit  



The industry standard is the \*\*3-2-1 rule\*\*:

\- 3 copies of your data  

\- 2 different types of storage  

\- 1 copy offsite  



GhostBackup gives you the first two. This guide helps you complete the third.



\---



\## Why This Is Already Safe



GhostBackup encrypts every file before writing it to your SSD. The files on your backup drive are not your original documents — they are `.ghostenc` files, encrypted with AES-256-GCM.



This means:



\- No cloud provider can read them  

\- No sync service can index or scan their contents  

\- No one who finds a USB drive with your backups can open them  

\- Without your encryption key, they are random bytes  



You are not uploading sensitive data to the cloud. You are uploading encrypted blobs that are meaningless to anyone without your key. This is a standard approach used in many secure backup systems.



\---



\## Option A: Cloud Sync — OneDrive / Dropbox / Google Drive (Recommended for most users)



The simplest approach. Point your existing cloud sync client at your GhostBackup folder and let it handle the rest.



\### Steps



1\. Open your cloud sync app (OneDrive, Dropbox, or Google Drive for Desktop)  

2\. Make sure your GhostBackup folder (e.g., `D:\\GhostBackup`) is inside your cloud sync folder, or configure your sync app to include it  

3\. Let the initial sync complete — this may take hours depending on backup size  

4\. After each backup run, new and changed `.ghostenc` files sync automatically  



\### Things to Know



| Consideration | Detail |

|--------------|--------|

| Storage quota | Your cloud storage needs to be at least as large as your backup SSD usage. Check the GhostBackup Dashboard for current size. |

| Initial sync | If you have 20GB+ of existing backups, the first sync will take a while. Run it overnight. |

| Two-way sync | If GhostBackup prunes old backups, a two-way sync will also delete them from the cloud. If your provider supports one-way upload, prefer that. |

| Bandwidth | Syncing runs in the background. On slow connections, it may take several hours after each backup run. This does not affect GhostBackup itself. |



\---



\## Option B: USB / External Drive Rotation



For offices that prefer physical offsite copies without any cloud involvement.



\### Steps



Robocopy is a built-in Windows tool that copies and keeps folders in sync. No installation required.



1\. Get one or two USB external drives (SSD recommended)  

2\. Plug in the drive  

3\. Open Command Prompt and run:  

robocopy "D:\\GhostBackup" "F:\\GhostBackup-Offsite" /MIR /R:3 /W:5  

4\. Replace paths as needed  

5\. Wait for the copy to complete  

6\. Eject the drive and store it offsite — at home, in a safe, or another office  



\### Recommended Schedule



| Frequency | Good For |

|----------|----------|

| Weekly | Most small businesses |

| Daily | High data change |

| Monthly | Low-volume data |



If you have two drives, rotate them so one is always offsite.



\---



\## Option C: Copy to a Second Machine on the Network



For offices with a second PC, server, or NAS.



\### Steps



Robocopy is a built-in Windows tool that copies and keeps folders in sync.



1\. Ensure the destination has a shared folder  

2\. Open Command Prompt and run:  

robocopy "D:\\GhostBackup" "\\\\OFFICE-PC2\\Backups\\GhostBackup" /MIR /R:3 /W:5  

3\. Replace the network path as needed  

4\. Optionally automate with Task Scheduler (e.g., 1 hour after backup)



\*\*Note:\*\* GhostBackup does not support network drives directly. This works because you're copying already-encrypted files.



\---



\## What NOT to Do



| Rule | Why |

|------|-----|

| Do NOT copy `.env.local` | It may contain your encryption key |

| Do NOT store key with backups | Anyone with both can decrypt everything |

| Do NOT rely only on offsite | Local SSD is your primary restore source |

| Do NOT upload raw files | Only sync `.ghostenc` files |



\---



\## Recommended Setup



Follow the 3-2-1 rule:



| Copy | Location | Purpose | Managed By |

|------|----------|---------|------------|

| Original | Source machine | Working files | You |

| Local backup | Primary SSD | Fast restore | GhostBackup |

| Offsite copy | Cloud / USB / network | Disaster recovery | You |



If using a secondary SSD, you have 4 copies — even better.



\---



\## FAQ



\*\*Q: Can the cloud provider read my files?\*\*  

A: No. They are AES-256-GCM encrypted. Without your key, they are random data.



\*\*Q: What if I lose my encryption key?\*\*  

A: All backups become permanently unrecoverable. Back it up securely.



\*\*Q: Do I need to change any GhostBackup settings?\*\*  

A: No. This works with your existing setup.



\*\*Q: How much cloud storage do I need?\*\*  

A: Roughly equal to your backup SSD usage.



\*\*Q: Will this slow down backups?\*\*  

A: No. Sync happens after GhostBackup finishes.



\*\*Q: What happens when backups are pruned?\*\*  

A: Two-way sync will delete them in the cloud as well. Use one-way sync or USB if you want longer retention.



\---



👻 GhostBackup — your files never leave your control, even when they leave your building.

