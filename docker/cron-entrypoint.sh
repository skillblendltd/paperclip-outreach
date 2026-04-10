#!/bin/bash
# Cron container entrypoint - installs cron jobs and runs cron in foreground
set -e

echo "[$(date)] Cron container starting..."

# Create log files
touch /tmp/campaigns_daily.log
touch /tmp/outreach_reply_monitor.log
touch /tmp/outreach_cron.log

# Write cron jobs
cat > /etc/cron.d/outreach << 'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Send sequences daily at 11am Mon-Fri
0 11 * * 1-5 root cd /app && python manage.py send_sequences >> /tmp/campaigns_daily.log 2>&1

# Check replies every 10 minutes
*/10 * * * * root cd /app && python manage.py handle_replies >> /tmp/outreach_reply_monitor.log 2>&1

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
