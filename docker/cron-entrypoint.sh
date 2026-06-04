#!/bin/bash
# Cron container entrypoint - installs cron jobs and runs cron in foreground
set -e

echo "[$(date)] Cron container starting..."

# Dump container environment to a file that cron jobs can source.
# Docker cron runs in a minimal env and doesn't inherit container vars.
env | grep -v '^_=' | grep -v '^HOSTNAME=' | grep -v '^HOME=' \
    | sed 's/"/\\"/g; s/\(.*\)=\(.*\)/export \1="\2"/' > /app/docker/.env.cron
chmod 600 /app/docker/.env.cron
echo "[$(date)] Environment exported to /app/docker/.env.cron"

# Create log files
touch /tmp/campaigns_daily.log
touch /tmp/outreach_reply_monitor.log
touch /tmp/outreach_cron.log
touch /tmp/outreach_call_queue.log

# Write cron jobs - source env before each command
cat > /etc/cron.d/outreach << 'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Send sequences daily at 11am Mon-Fri. CRON_SEND_ARGS lets each host scope itself
# (e.g. EC2 uses --product print-promo, laptop uses --exclude-product print-promo)
0 11 * * 1-5 root . /app/docker/.env.cron && cd /app && python manage.py send_sequences ${CRON_SEND_ARGS:-} >> /tmp/campaigns_daily.log 2>&1

# Check replies every 10 minutes. CRON_REPLY_ARGS scopes the same way.
*/10 * * * * root . /app/docker/.env.cron && cd /app && python manage.py handle_replies ${CRON_REPLY_ARGS:-} >> /tmp/outreach_reply_monitor.log 2>&1

# Post to social media daily at 9am Mon-Fri (all products with scheduled posts)
0 9 * * 1-5 root . /app/docker/.env.cron && cd /app && python manage.py publish_post --next-scheduled >> /tmp/outreach_social.log 2>&1

# Nudge stale warm leads + reactivate follow_up_later — 30 min after send_sequences
30 11 * * 1-5 root . /app/docker/.env.cron && cd /app && python manage.py nudge_stale_leads ${CRON_SEND_ARGS:-} >> /tmp/outreach_nudge.log 2>&1

# Daily KPI email at 8am Mon-Fri
0 8 * * 1-5 root . /app/docker/.env.cron && cd /app && python manage.py daily_kpi_email >> /tmp/outreach_kpi.log 2>&1

# Weekly digests - every Friday 5pm Dublin time
# Tenant isolation: each line targets ONE campaign, recipients see only that campaign's data
# Add a new campaign digest by adding another line with its --campaign-id and --to
# FP UK -> Prakash + Jamal
0 17 * * 5 root . /app/docker/.env.cron && cd /app && python manage.py send_weekly_digest --campaign-id 3e5a0d4b-777a-4c74-855c-ac9b10c76dad --to "prakash@taggiq.com,shah.jamal@fullypromoted.co.uk" >> /tmp/outreach_weekly_digest.log 2>&1

# Health check at 8am daily (including weekends)
0 8 * * * root . /app/docker/.env.cron && cd /app && python manage.py brain_doctor >> /tmp/outreach_health.log 2>&1

# Process the warm-lead call queue every 5 minutes (Sprint 9).
# Picks pending CallTask rows whose scheduled_for has elapsed and dispatches
# via the configured call provider (Vapi today; provider-agnostic boundary).
*/5 * * * * root . /app/docker/.env.cron && cd /app && python manage.py process_call_queue >> /tmp/outreach_call_queue.log 2>&1

# Poll SES bounce SQS queue every 15 minutes.
# Receives Bounce/Complaint/Reject events from the paperclip-bounces config set,
# auto-creates Suppressions and disables matching Prospects.
*/15 * * * * root . /app/docker/.env.cron && cd /app && python manage.py process_ses_bounces >> /tmp/outreach_bounces.log 2>&1

# Daily bounce-rate audit at 8:15am (15 min after brain_doctor).
# Reports bounce/complaint rates per sending domain, alerts on threshold breach.
15 8 * * * root . /app/docker/.env.cron && cd /app && python manage.py bounce_audit >> /tmp/outreach_bounces_audit.log 2>&1

# Nightly backup at 23:00
0 23 * * * root . /app/docker/.env.cron && cd /app && /app/backup_to_gdrive.sh >> /tmp/outreach_backup.log 2>&1

# Empty line required at end
EOF

chmod 0644 /etc/cron.d/outreach

# Start cron in foreground (so container stays alive)
echo "[$(date)] Cron jobs installed:"
cat /etc/cron.d/outreach
echo ""
echo "[$(date)] Starting cron daemon..."

# Run cron in foreground
cron -f -L 15
