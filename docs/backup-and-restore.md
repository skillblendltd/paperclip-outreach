# Backup & Restore Guide

## What gets backed up

| Data | Location | In GitHub? |
|------|----------|-----------|
| SQLite DB (prospects, opt-outs, email logs, statuses) | `db/outreach.sqlite3` | No — backed up here |
| Scraped CSV files | `google-maps-scraper/output/*.csv` | No — backed up here |
| Code | All `.py`, config files | Yes — GitHub |

**The DB is the most critical asset.** It contains every prospect status, opt-out, reply thread, and campaign history. It cannot be re-created from scratch.

---

## Backup setup

### Tools

- **rclone** — syncs local files to Google Drive
- **cron** — runs the backup nightly at 11pm
- **SQLite `.backup`** — atomic backup safe to run while campaigns are live

### Schedule

```
0 23 * * *  /Users/pinani/Documents/paperclip-outreach/backup_to_gdrive.sh
```

Runs every night at 11pm. Backs up DB + all CSVs to:
```
gdrive:/paperclip-outreach-backup/
```

Google Drive keeps 30 days of version history natively — so you have a 30-day restore window.

### SQLite WAL mode

WAL mode is enabled on the DB (set once, persistent). Allows safe concurrent reads during backups without locking the campaigns.

```bash
sqlite3 db/outreach.sqlite3 "PRAGMA journal_mode;"
# Should return: wal
```

---

## Setting up rclone on a new machine

Run this once after cloning the repo on a new machine.

### 1. Install rclone

```bash
brew install rclone
```

### 2. Configure Google Drive remote

```bash
rclone config
```

Follow the prompts:
1. `n` — New remote
2. Name: `gdrive`
3. Storage type: `drive`
4. Client ID: press Enter (leave blank)
5. Client Secret: press Enter (leave blank)
6. Scope: `1` (full access)
7. Root folder ID: press Enter (leave blank)
8. Service account file: press Enter (leave blank)
9. Edit advanced config: `n`
10. Use auto config: `y` — browser opens, sign in with Prakash's Google account
11. Configure as Team Drive: `n`
12. Confirm: `y`
13. `q` — Quit config

### 3. Verify the connection

```bash
rclone lsd gdrive:
```

Should list your Google Drive folders.

### 4. Install the cron job

```bash
(crontab -l 2>/dev/null; echo "0 23 * * * /Users/pinani/Documents/paperclip-outreach/backup_to_gdrive.sh") | crontab -
```

### 5. Run a manual backup to verify

```bash
cd /Users/pinani/Documents/paperclip-outreach
bash backup_to_gdrive.sh
```

Check the log:
```bash
cat /tmp/paperclip_backup.log | tail -10
```

---

## Restoring from backup

### Full restore (new machine or after crash)

```bash
# 1. Clone the code
git clone https://github.com/skillblendltd/paperclip-outreach.git
cd paperclip-outreach

# 2. Install rclone and configure gdrive remote (see setup above)

# 3. Download the backup from Google Drive
rclone copy gdrive:/paperclip-outreach-backup/db/outreach.sqlite3 db/
rclone copy gdrive:/paperclip-outreach-backup/output/ google-maps-scraper/output/

# 4. Verify the DB is intact
sqlite3 db/outreach.sqlite3 "SELECT count(*) FROM campaigns_prospect;"
# Should return a number > 0

# 5. Set up Python environment
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 6. Run the server
venv/bin/python manage.py runserver 8002
```

### Restore to a specific date

Google Drive keeps 30 days of file version history. To restore an older version:

1. Go to [drive.google.com](https://drive.google.com)
2. Navigate to `paperclip-outreach-backup/db/`
3. Right-click `outreach.sqlite3` → Manage versions
4. Download the version from the date you want
5. Replace `db/outreach.sqlite3` with the downloaded file

### Verify the restored DB

```bash
sqlite3 db/outreach.sqlite3 "
SELECT count(*) as prospects FROM campaigns_prospect;
SELECT count(*) as sent FROM campaigns_emaillog WHERE status='sent';
SELECT count(*) as opted_out FROM campaigns_prospect WHERE status='opt_out';
"
```

---

## Checking backup status

```bash
# View recent backup logs
cat /tmp/paperclip_backup.log | tail -20

# Check what's on Google Drive
rclone ls gdrive:/paperclip-outreach-backup

# Run a manual backup right now
bash /Users/pinani/Documents/paperclip-outreach/backup_to_gdrive.sh

# Check cron jobs
crontab -l
```

---

## Cron jobs reference

| Schedule | Script | Purpose |
|----------|--------|---------|
| `*/10 * * * *` | `run_reply_monitor.sh` | Check TaggIQ mailbox for replies every 10 min |
| `0 23 * * *` | `backup_to_gdrive.sh` | Nightly backup to Google Drive at 11pm |
