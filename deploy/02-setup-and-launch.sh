#!/bin/bash
# =============================================================================
# Step 2: Setup server, migrate data, and launch
# Combines old steps 2+3 into one script. No Nginx, no SSL, no domain.
#
# Usage: bash deploy/02-setup-and-launch.sh <ELASTIC_IP>
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
    echo "Usage: bash deploy/02-setup-and-launch.sh <ELASTIC_IP>"
    exit 1
fi

echo "============================================"
echo "  PAPERCLIP OUTREACH - SETUP + MIGRATION"
echo "============================================"
echo ""
echo "  Target: $IP"
echo "  This will:"
echo "    1. Install Docker on EC2"
echo "    2. Clone repo + copy .env"
echo "    3. Stop local cron"
echo "    4. Dump + transfer + restore data"
echo "    5. Launch Docker stack on EC2"
echo ""
read -p "  Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# ── Phase A: Server Setup ──────────────────────────────────────────────

echo ""
echo "[1/9] Installing Docker on EC2..."
$SSH << 'REMOTE'
sudo dnf update -y -q 2>/dev/null
sudo dnf install -y -q docker git
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Docker Compose plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -sL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

echo "Docker $(docker --version | grep -oP '[0-9]+\.[0-9]+\.[0-9]+')"
echo "Compose $(docker compose version --short)"
REMOTE

echo ""
echo "[2/9] Cloning repo..."
$SSH << 'REMOTE'
if [ -d ~/paperclip-outreach ]; then
    cd ~/paperclip-outreach && git pull --ff-only
else
    git clone https://github.com/skillblendltd/paperclip-outreach.git ~/paperclip-outreach
fi
REMOTE

echo ""
echo "[3/9] Copying .env + generating webhook secret..."
$SCP $LOCAL_DIR/.env ec2-user@$IP:~/paperclip-outreach/.env

# Generate and append webhook secret
WEBHOOK_SECRET=$(openssl rand -hex 32)
$SSH "echo 'TAGGIQ_WEBHOOK_SECRET=$WEBHOOK_SECRET' >> ~/paperclip-outreach/.env"

echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │ SAVE THIS - add to TaggIQ .env on production:      │"
echo "  │                                                     │"
echo "  │ OUTREACH_WEBHOOK_SECRET=$WEBHOOK_SECRET             │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""

# ── Phase B: Data Migration ────────────────────────────────────────────

echo "[4/9] Checking for running local jobs..."
if [ -f /tmp/campaigns_daily.lock ] || [ -f /tmp/outreach_reply_monitor.lock ]; then
    echo "  WARNING: A job is running. Wait for it to finish, then re-run this script."
    exit 1
fi
echo "  No running jobs."

echo ""
echo "[5/9] Stopping local cron..."
crontab -l 2>/dev/null | sed 's|^\(.*/paperclip-outreach/.*\)|# MIGRATED: \1|' | crontab -
echo "  Local cron disabled"

echo ""
echo "[6/9] Dumping local PostgreSQL..."
cd $LOCAL_DIR
docker exec outreach_db pg_dump -U outreach -d outreach --clean --if-exists > /tmp/outreach_migration.sql
echo "  Dump: $(du -sh /tmp/outreach_migration.sql | cut -f1)"

echo ""
echo "[7/9] Transferring to EC2..."
$SCP /tmp/outreach_migration.sql ec2-user@$IP:~/outreach_migration.sql
echo "  Transfer complete"

echo ""
echo "[8/9] Restoring on EC2 + starting services..."
$SSH << 'REMOTE'
cd ~/paperclip-outreach

# Need to reconnect as docker group member
newgrp docker << 'DOCKERCMDS'
cd ~/paperclip-outreach

# Start PostgreSQL
docker compose up -d postgres
echo "Waiting for PostgreSQL..."
sleep 5
docker compose exec -T postgres pg_isready -U outreach

# Restore data
docker exec -i outreach_db psql -U outreach -d outreach < ~/outreach_migration.sql 2>&1 | tail -3

# Start everything
docker compose up -d --build
sleep 5
docker compose ps
DOCKERCMDS
REMOTE

echo ""
echo "[9/9] Verifying..."
$SSH << 'REMOTE'
newgrp docker << 'DOCKERCMDS'
cd ~/paperclip-outreach

echo "=== Data ==="
docker exec outreach_web python manage.py shell -c "
from campaigns.models import Campaign, Prospect, EmailLog, EmailTemplate
print(f'Campaigns: {Campaign.objects.count()}')
print(f'Prospects: {Prospect.objects.count()}')
print(f'Emails sent: {EmailLog.objects.filter(status=\"sent\").count()}')
print(f'Templates: {EmailTemplate.objects.count()}')
"

echo ""
echo "=== Django Check ==="
docker exec outreach_web python manage.py check

echo ""
echo "=== Cron ==="
docker exec outreach_cron cat /etc/cron.d/outreach
DOCKERCMDS
REMOTE

PRIVATE_IP=$($SSH "hostname -I | awk '{print \$1}'" 2>/dev/null)

echo ""
echo "============================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================"
echo ""
echo "  Paperclip is live on EC2."
echo "  Local cron is disabled."
echo ""
echo "  Add to TaggIQ .env:"
echo "    OUTREACH_WEBHOOK_URL=http://${PRIVATE_IP:-<PRIVATE_IP>}:8002/api/webhooks/taggiq/"
echo "    OUTREACH_WEBHOOK_SECRET=$WEBHOOK_SECRET"
echo ""
echo "  Update Vapi dashboard webhook URL:"
echo "    http://$IP:8002/api/webhooks/vapi/"
echo ""
echo "  Admin:    http://$IP:8002/admin/"
echo "  Dashboard: http://$IP:8002/api/dashboard/"
echo ""
echo "  Monitor:"
echo "    ssh -i ~/.ssh/$KEY.pem ec2-user@$IP"
echo "    docker logs -f outreach_cron"
echo ""
echo "  Rollback:"
echo "    1. ssh ... 'cd paperclip-outreach && docker compose down'"
echo "    2. crontab -e (uncomment local Paperclip lines)"
echo ""
