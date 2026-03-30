#!/bin/bash
# TaggIQ Reply Monitor — check_replies + log flagged for manual /taggiq-email-expert
cd /Users/pinani/Documents/paperclip-outreach

LOGFILE="/tmp/taggiq_reply_monitor.log"
echo "" >> "$LOGFILE"
echo "[$(date)] === Reply check ===" >> "$LOGFILE"

# Step 1: fetch new inbound emails from Zoho IMAP
venv/bin/python manage.py check_replies --mailbox taggiq >> "$LOGFILE" 2>&1

# Step 2: count flagged
FLAGGED=$(venv/bin/python manage.py shell -c "
from campaigns.models import InboundEmail
n = InboundEmail.objects.filter(needs_reply=True, replied=False, campaign__product='taggiq').count()
print(n)
" 2>/dev/null)

echo "[$(date)] Flagged needing reply: $FLAGGED" >> "$LOGFILE"

if [ "$FLAGGED" -gt 0 ]; then
    echo "[$(date)] ACTION REQUIRED: $FLAGGED email(s) need reply — run /taggiq-email-expert" >> "$LOGFILE"
    # macOS notification
    osascript -e "display notification \"$FLAGGED TaggIQ email(s) need reply\" with title \"TaggIQ Reply Needed\"" 2>/dev/null || true
fi

echo "[$(date)] Done" >> "$LOGFILE"
