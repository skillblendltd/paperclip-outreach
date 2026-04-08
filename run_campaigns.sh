#!/bin/bash
# =============================================================================
# Master Campaign Runner - runs daily via cron
# Sends all due sequences across ALL campaigns autonomously using the
# universal sender (send_sequences). DB-driven templates, send windows,
# rate limiting. Replaces the old 3-script approach.
#
# Cron: 0 11 * * 1-5 /Users/pinani/Documents/paperclip-outreach/run_campaigns.sh
#
# What this does:
#   1. Runs send_sequences for all active campaigns (TaggIQ + FP + any future)
#   2. Send windows, batch sizes, delays all configured per campaign in DB
#   3. Logs to /tmp/campaigns_daily.log
#   4. macOS notification on completion
# =============================================================================

cd /Users/pinani/Documents/paperclip-outreach

LOGFILE="/tmp/campaigns_daily.log"
LOCK="/tmp/campaigns_daily.lock"

# Prevent overlapping runs
if [ -f "$LOCK" ]; then
    echo "[$(date)] Already running - skipping" >> "$LOGFILE"
    exit 0
fi
touch "$LOCK"
trap "rm -f $LOCK" EXIT

echo "" >> "$LOGFILE"
echo "============================================================" >> "$LOGFILE"
echo "[$(date)] Daily campaign run starting (universal sender)" >> "$LOGFILE"
echo "============================================================" >> "$LOGFILE"

venv/bin/python manage.py send_sequences >> "$LOGFILE" 2>&1
EXIT_CODE=$?

echo "[$(date)] Universal sender done (exit $EXIT_CODE)" >> "$LOGFILE"

# Count today's sends from log
TODAY_SENT=$(grep -c "SENT \[" "$LOGFILE" 2>/dev/null | tail -1 || echo 0)

osascript -e "display notification \"Daily send complete - ${TODAY_SENT} emails\" with title \"Outreach Campaigns\"" 2>/dev/null || true

echo "[$(date)] Done. Today's sends: ${TODAY_SENT}" >> "$LOGFILE"
