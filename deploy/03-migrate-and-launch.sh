#!/bin/bash
# =============================================================================
# Step 3: Migrate data and launch Paperclip on EC2
# This is the critical switchover script. Total downtime: ~30 minutes.
#
# Usage: bash deploy/03-migrate-and-launch.sh <ELASTIC_IP>
#
# IMPORTANT: This script will:
#   1. Stop local cron (your Mac stops sending)
#   2. Dump local PostgreSQL
#   3. Transfer to EC2
#   4. Restore on EC2
#   5. Start EC2 Docker stack
#   6. Verify everything
# =============================================================================

set -e

if [ -f deploy/.ec2-config ]; then
    source deploy/.ec2-config
fi

IP="${1:-$ELASTIC_IP}"
KEY="${KEY_NAME:-outreach-key}"
SSH="ssh -i ~/.ssh/$KEY.pem -o StrictHostKeyChecking=no ec2-user@$IP"
SCP="scp -i ~/.ssh/$KEY.pem -o StrictHostKeyChecking=no"
LOCAL_DIR="/Users/pinani/Documents/paperclip-outreach"

if [ -z "$IP" ]; then
    echo "Usage: bash deploy/03-migrate-and-launch.sh <ELASTIC_IP>"
    exit 1
fi

echo "============================================"
echo "  PAPERCLIP OUTREACH - DATA MIGRATION"
echo "============================================"
echo ""
echo "  Source: Local Docker PostgreSQL"
echo "  Target: EC2 at $IP"
echo ""
echo "  This will STOP local cron and move all data to AWS."
echo "  Current campaigns will resume on EC2."
echo ""
read -p "  Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "[1/8] Checking for running jobs..."
if [ -f /tmp/campaigns_daily.lock ]; then
    echo "  WARNING: Campaign send is running. Wait for it to finish."
    echo "  Lock file: /tmp/campaigns_daily.lock"
    exit 1
fi
if [ -f /tmp/outreach_reply_monitor.lock ]; then
    echo "  WARNING: Reply monitor is running. Wait for it to finish."
    exit 1
fi
echo "  No running jobs. Safe to proceed."

echo ""
echo "[2/8] Stopping local cron..."
# Comment out Paperclip cron jobs
crontab -l 2>/dev/null | sed 's|^\(.*/paperclip-outreach/.*\)|# MIGRATED TO AWS: \1|' | crontab -
echo "  Local cron disabled"

echo ""
echo "[3/8] Dumping local PostgreSQL..."
cd $LOCAL_DIR
docker exec outreach_db pg_dump -U outreach -d outreach --clean --if-exists > /tmp/outreach_migration.sql
DUMP_SIZE=$(du -sh /tmp/outreach_migration.sql | cut -f1)
echo "  Dump created: $DUMP_SIZE"

echo ""
echo "[4/8] Transferring to EC2..."
$SCP /tmp/outreach_migration.sql ec2-user@$IP:~/outreach_migration.sql
echo "  Transfer complete"

echo ""
echo "[5/8] Starting PostgreSQL on EC2..."
$SSH << 'REMOTE'
cd ~/paperclip-outreach
# Start only postgres first
docker compose up -d postgres
echo "Waiting for PostgreSQL to be healthy..."
sleep 5
docker compose exec -T postgres pg_isready -U outreach
echo "PostgreSQL is ready"
REMOTE

echo ""
echo "[6/8] Restoring data on EC2..."
$SSH << 'REMOTE'
cd ~/paperclip-outreach
# Restore the dump
docker exec -i outreach_db psql -U outreach -d outreach < ~/outreach_migration.sql 2>&1 | tail -5
echo "Data restored"
REMOTE

echo ""
echo "[7/8] Starting all services on EC2..."
$SSH << 'REMOTE'
cd ~/paperclip-outreach
docker compose up -d
sleep 5
docker compose ps
REMOTE

echo ""
echo "[8/8] Verifying deployment..."
$SSH << 'REMOTE'
cd ~/paperclip-outreach

echo ""
echo "=== Data Verification ==="
docker exec outreach_web python manage.py shell -c "
from campaigns.models import *
print(f'Organizations: {Organization.objects.count()}')
print(f'Products: {Product.objects.count()}')
print(f'Campaigns: {Campaign.objects.count()}')
print(f'Prospects: {Prospect.objects.count()}')
print(f'EmailTemplates: {EmailTemplate.objects.count()}')
print(f'EmailLog: {EmailLog.objects.count()}')
print(f'InboundEmail: {InboundEmail.objects.count()}')
print(f'Suppressions: {Suppression.objects.count()}')
for c in Campaign.objects.all().order_by('name'):
    total = Prospect.objects.filter(campaign=c).count()
    sent = EmailLog.objects.filter(campaign=c, status='sent').count()
    print(f'  {c.name}: {total} prospects, {sent} sent')
"

echo ""
echo "=== Django Check ==="
docker exec outreach_web python manage.py check

echo ""
echo "=== Dry Run ==="
docker exec outreach_web python manage.py send_sequences --dry-run --status 2>&1 | grep -E "(Campaign:|TOTAL|eligible)"

echo ""
echo "=== Cron Jobs ==="
docker exec outreach_cron cat /etc/cron.d/outreach
REMOTE

echo ""
echo "============================================"
echo "  MIGRATION COMPLETE"
echo "============================================"
echo ""
echo "  Paperclip Outreach is now running on EC2."
echo "  Local cron has been disabled."
echo ""
echo "  VERIFY:"
echo "    curl https://outreach.taggiq.com/api/dashboard/"
echo "    curl https://outreach.taggiq.com/api/webhooks/taggiq/ (should return 405)"
echo ""
echo "  MONITOR (first 3 days):"
echo "    ssh -i ~/.ssh/$KEY.pem ec2-user@$IP"
echo "    docker logs -f outreach_cron"
echo "    docker exec outreach_cron cat /tmp/campaigns_daily.log"
echo "    docker exec outreach_cron cat /tmp/outreach_reply_monitor.log"
echo ""
echo "  ROLLBACK (if needed):"
echo "    1. Stop EC2: ssh ... 'cd paperclip-outreach && docker compose down'"
echo "    2. Re-enable local cron: crontab -e (uncomment Paperclip lines)"
echo ""
echo "  VAPI WEBHOOK:"
echo "    Update Vapi dashboard webhook URL to:"
echo "    https://outreach.taggiq.com/api/webhooks/vapi/"
echo ""
