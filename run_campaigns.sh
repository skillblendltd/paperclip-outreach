#!/bin/bash
# =============================================================================
# Master Campaign Runner — runs daily via cron
# Sends all due sequences across all TaggIQ campaigns autonomously.
#
# Cron: 0 11 * * 1-5 /Users/pinani/Documents/paperclip-outreach/run_campaigns.sh
#
# What this does:
#   1. BNI campaigns (BNI Ireland, Promo Global, Embroidery Global)
#      → send_sequence.py handles seq 1–5, 7-day gaps enforced by API
#   2. Ireland cold campaigns (Signs, Apparel, Print & Promo)
#      → send_ireland_sequences.py handles seq 1–5, 7-day gaps enforced locally
#   3. London cold campaigns (Signs, Apparel, Print & Promo)
#      → send_london_sequences.py handles seq 1–5, 7-day gaps enforced locally
#   4. Logs everything to /tmp/campaigns_daily.log
#   5. macOS notification on completion
# =============================================================================

cd /Users/pinani/Documents/paperclip-outreach

LOGFILE="/tmp/campaigns_daily.log"
LOCK="/tmp/campaigns_daily.lock"

# Prevent overlapping runs
if [ -f "$LOCK" ]; then
    echo "[$(date)] Already running — skipping" >> "$LOGFILE"
    exit 0
fi
touch "$LOCK"
trap "rm -f $LOCK" EXIT

echo "" >> "$LOGFILE"
echo "============================================================" >> "$LOGFILE"
echo "[$(date)] Daily campaign run starting" >> "$LOGFILE"
echo "============================================================" >> "$LOGFILE"

# ── 1. BNI campaigns (all three) ─────────────────────────────────────────────
echo "" >> "$LOGFILE"
echo "[$(date)] Running BNI sequences..." >> "$LOGFILE"

venv/bin/python bni-scraper/send_sequence.py >> "$LOGFILE" 2>&1
BNI_EXIT=$?
echo "[$(date)] BNI sequences done (exit $BNI_EXIT)" >> "$LOGFILE"

# ── 2. Ireland cold campaigns (all three) ────────────────────────────────────
echo "" >> "$LOGFILE"
echo "[$(date)] Running Ireland cold sequences..." >> "$LOGFILE"

venv/bin/python google-maps-scraper/send_ireland_sequences.py >> "$LOGFILE" 2>&1
IRELAND_EXIT=$?
echo "[$(date)] Ireland sequences done (exit $IRELAND_EXIT)" >> "$LOGFILE"

# ── 3. London cold campaigns (all three) ─────────────────────────────────────
echo "" >> "$LOGFILE"
echo "[$(date)] Running London cold sequences..." >> "$LOGFILE"

venv/bin/python google-maps-scraper/send_london_sequences.py >> "$LOGFILE" 2>&1
LONDON_EXIT=$?
echo "[$(date)] London sequences done (exit $LONDON_EXIT)" >> "$LOGFILE"

# ── 4. Summary notification ───────────────────────────────────────────────────
SENT=$(grep -c "SENT \[" "$LOGFILE" 2>/dev/null | tail -1 || echo "?")
echo "" >> "$LOGFILE"
echo "[$(date)] Run complete." >> "$LOGFILE"

# Count today's sends from log
TODAY=$(date '+%a %d %b')
TODAY_SENT=$(grep "$TODAY" "$LOGFILE" 2>/dev/null | grep -c "SENT \[" || echo 0)

osascript -e "display notification \"Daily send complete — ${TODAY_SENT} emails sent today\" with title \"TaggIQ Campaigns\"" 2>/dev/null || true

echo "[$(date)] Done. Today's sends: ${TODAY_SENT}" >> "$LOGFILE"
