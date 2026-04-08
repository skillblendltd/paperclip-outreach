#!/bin/bash
# =============================================================================
# Reply Monitor - checks all mailboxes, invokes AI reply per product
# Uses DB-driven PromptTemplate for per-product voice (Lisa, Prakash, etc.)
# Falls back to skill files (/taggiq-email-expert, /fp-email-expert) if no DB prompt
#
# Cron: */10 * * * * /Users/pinani/Documents/paperclip-outreach/run_reply_monitor.sh
# =============================================================================

cd /Users/pinani/Documents/paperclip-outreach

LOGFILE="/tmp/outreach_reply_monitor.log"
LOCK_FILE="/tmp/outreach_reply_monitor.lock"

# Prevent overlapping runs
if [ -f "$LOCK_FILE" ]; then
    echo "[$(date)] Already running (lock exists), skipping" >> "$LOGFILE"
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

echo "" >> "$LOGFILE"
echo "[$(date)] === Reply monitor ===" >> "$LOGFILE"

venv/bin/python manage.py handle_replies >> "$LOGFILE" 2>&1
EXIT_CODE=$?

echo "[$(date)] Done (exit $EXIT_CODE)" >> "$LOGFILE"

# Count remaining
REMAINING=$(venv/bin/python manage.py shell -c "
from campaigns.models import InboundEmail
n = InboundEmail.objects.filter(needs_reply=True, replied=False).count()
print(n)
" 2>/dev/null)

if [ "$REMAINING" -gt 0 ]; then
    osascript -e "display notification \"$REMAINING reply(s) still need attention\" with title \"Outreach Reply Monitor\"" 2>/dev/null || true
    echo "[$(date)] $REMAINING still pending" >> "$LOGFILE"
fi
