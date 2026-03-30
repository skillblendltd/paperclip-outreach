#!/bin/bash
# ── Paperclip Outreach — Daily Data Backup ───────────────────────────────────
# Runs nightly at 11pm via cron.
#   - SQLite .backup (atomic, safe while campaigns are running)
#   - Syncs DB + CSVs to Google Drive (30-day version history built-in)
#
# Setup (one-time):
#   brew install rclone
#   rclone config  →  name it "gdrive", type "drive", follow OAuth
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_DIR="/Users/pinani/Documents/paperclip-outreach"
BACKUP_DIR="$PROJECT_DIR/backups"
GDRIVE_DEST="gdrive:/paperclip-outreach-backup"
LOGFILE="/tmp/paperclip_backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"
}

mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/output"
log "=== Daily backup started ==="

# ── 1. Atomic SQLite backup ───────────────────────────────────────────────────
DB_SRC="$PROJECT_DIR/db/outreach.sqlite3"
DB_DEST="$BACKUP_DIR/db/outreach.sqlite3"

if [ -f "$DB_SRC" ]; then
    sqlite3 "$DB_SRC" ".backup '$DB_DEST'"
    log "DB backed up: $(du -sh "$DB_DEST" | cut -f1)"
else
    log "ERROR: DB not found at $DB_SRC"
    exit 1
fi

# ── 2. Copy CSV outputs ───────────────────────────────────────────────────────
cp "$PROJECT_DIR"/google-maps-scraper/output/*.csv "$BACKUP_DIR/output/" 2>/dev/null || true
CSV_COUNT=$(ls "$BACKUP_DIR/output/"*.csv 2>/dev/null | wc -l | tr -d ' ')
log "CSVs backed up: $CSV_COUNT files"

# ── 3. Sync to Google Drive ───────────────────────────────────────────────────
if ! command -v rclone &>/dev/null; then
    log "ERROR: rclone not installed. Run: brew install rclone && rclone config"
    exit 1
fi

rclone sync "$BACKUP_DIR" "$GDRIVE_DEST" \
    --log-file="$LOGFILE" \
    --log-level NOTICE \
    --transfers 4 \
    --retries 3

log "=== Backup complete → $GDRIVE_DEST ==="

tail -1000 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
