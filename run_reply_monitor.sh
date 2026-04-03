#!/bin/bash
# TaggIQ Reply Monitor — check_replies + autonomous Claude reply via claude CLI
cd /Users/pinani/Documents/paperclip-outreach

LOGFILE="/tmp/taggiq_reply_monitor.log"
CLAUDE_LOG="/tmp/taggiq_claude_replies.log"
LOCK_FILE="/tmp/taggiq_reply_monitor.lock"

# Prevent overlapping runs
if [ -f "$LOCK_FILE" ]; then
    echo "[$(date)] Already running (lock exists), skipping" >> "$LOGFILE"
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

echo "" >> "$LOGFILE"
echo "[$(date)] === Reply check ===" >> "$LOGFILE"

# Step 1: fetch new inbound emails from Zoho IMAP
venv/bin/python manage.py check_replies --mailbox taggiq >> "$LOGFILE" 2>&1

# Step 2: count flagged emails needing reply
FLAGGED=$(venv/bin/python manage.py shell -c "
from campaigns.models import InboundEmail
n = InboundEmail.objects.filter(needs_reply=True, replied=False, campaign__product='taggiq').count()
print(n)
" 2>/dev/null)

echo "[$(date)] Flagged needing reply: $FLAGGED" >> "$LOGFILE"

if [ "$FLAGGED" -gt 0 ]; then
    echo "[$(date)] Invoking Claude to handle $FLAGGED email(s) autonomously..." >> "$LOGFILE"

    # macOS notification
    osascript -e "display notification \"Handling $FLAGGED TaggIQ reply(s) autonomously\" with title \"TaggIQ Auto-Reply\"" 2>/dev/null || true

    # Invoke Claude CLI with taggiq-email-expert skill
    echo "" >> "$CLAUDE_LOG"
    echo "[$(date)] === Claude auto-reply run ($FLAGGED flagged) ===" >> "$CLAUDE_LOG"

    /Users/pinani/.local/bin/claude \
        --model sonnet \
        --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
        --max-turns 30 \
        --output-format text \
        -p "/taggiq-email-expert" \
        >> "$CLAUDE_LOG" 2>&1

    EXIT_CODE=$?
    echo "[$(date)] Claude finished (exit $EXIT_CODE)" >> "$LOGFILE"

    # Check how many are still pending after Claude ran
    REMAINING=$(venv/bin/python manage.py shell -c "
from campaigns.models import InboundEmail
n = InboundEmail.objects.filter(needs_reply=True, replied=False, campaign__product='taggiq').count()
print(n)
" 2>/dev/null)

    echo "[$(date)] Remaining after Claude: $REMAINING" >> "$LOGFILE"

    if [ "$REMAINING" -gt 0 ]; then
        osascript -e "display notification \"$REMAINING email(s) still need manual review\" with title \"TaggIQ: Check Replies\"" 2>/dev/null || true
        echo "[$(date)] WARNING: $REMAINING still pending — may need manual review" >> "$LOGFILE"
    else
        osascript -e "display notification \"All $FLAGGED reply(s) sent successfully\" with title \"TaggIQ Auto-Reply Done\"" 2>/dev/null || true
    fi
fi

echo "[$(date)] Done" >> "$LOGFILE"
