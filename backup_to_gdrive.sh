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

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
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

# ── 3. Upload dated DB snapshot to Google Drive (keep 7 days) ────────────────
RCLONE=/opt/homebrew/bin/rclone
if [ ! -x "$RCLONE" ]; then
    log "ERROR: rclone not found at $RCLONE"
    exit 1
fi

TODAY=$(date '+%Y-%m-%d')
DATED_DEST="$GDRIVE_DEST/db/outreach_${TODAY}.sqlite3"

# Upload today's dated snapshot
$RCLONE copyto "$DB_DEST" "$DATED_DEST" \
    --log-file="$LOGFILE" \
    --log-level NOTICE \
    --retries 3
log "DB uploaded → $DATED_DEST"

# Upload CSVs
$RCLONE sync "$BACKUP_DIR/output" "$GDRIVE_DEST/output" \
    --log-file="$LOGFILE" \
    --log-level NOTICE \
    --transfers 4 \
    --retries 3
log "CSVs synced → $GDRIVE_DEST/output"

# Delete snapshots older than 7 days from Google Drive
log "Pruning snapshots older than 7 days..."
CUTOFF=$(date -v-7d '+%Y-%m-%d')
$RCLONE lsf "$GDRIVE_DEST/db/" --format "n" 2>/dev/null | grep "^outreach_.*\.sqlite3$" | while read fname; do
    FDATE=$(echo "$fname" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')
    if [ -n "$FDATE" ] && [[ "$FDATE" < "$CUTOFF" ]]; then
        $RCLONE deletefile "$GDRIVE_DEST/db/$fname" 2>/dev/null
        log "Deleted old snapshot: $fname"
    fi
done

log "=== Backup complete → $GDRIVE_DEST ==="

tail -1000 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
