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
        --allowedTools "Bash,Read,Write,Edit,Glob,Grep" \
        --max-turns 30 \
        --output-format text \
        -p "Run check_replies for the TaggIQ mailbox, then invoke /taggiq-email-expert to handle any flagged emails autonomously.

Step 1:
\`\`\`
cd /Users/pinani/Documents/paperclip-outreach && venv/bin/python manage.py check_replies --mailbox taggiq
\`\`\`

Step 2: Invoke /taggiq-email-expert to read all flagged TaggIQ inbound emails and send replies autonomously.

Step 3: After sending each reply, update the prospect's status in the DB based on what they said:
- They asked about pricing, features, or want a demo → status='interested'
- They booked or confirmed a demo time → status='demo_scheduled'
- They are actively engaging back and forth → status='engaged'
- They said not interested, too busy, wrong fit → status='not_interested', send_enabled=False
- They are a potential reseller/channel partner → status='design_partner'
- They just replied with a polite acknowledgement (no clear signal) → leave status as-is

Use this snippet for each prospect after replying:
\`\`\`
cd /Users/pinani/Documents/paperclip-outreach
venv/bin/python manage.py shell -c \"
from campaigns.models import Prospect
p = Prospect.objects.get(id='<PROSPECT_ID>')
p.status = '<NEW_STATUS>'
p.save(update_fields=['status', 'updated_at'])
print(f'Updated {p.business_name} -> {p.status}')
\"
\`\`\`

Also update notes with a brief summary of what they said, e.g.:
\`\`\`
p.notes = (p.notes or '') + '\n[2026-03-31] Replied asking about Solopress API integration.'
p.save(update_fields=['notes', 'updated_at'])
\`\`\`" \
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
