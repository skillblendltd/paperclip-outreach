#!/bin/bash
# =============================================================================
# Step 2: Set up the EC2 server (Docker, Nginx, SSL)
# Run this from your local machine after 01-provision-ec2.sh
#
# Usage: bash deploy/02-setup-server.sh <ELASTIC_IP>
# =============================================================================

set -e

# Load config from provisioning step
if [ -f deploy/.ec2-config ]; then
    source deploy/.ec2-config
fi

IP="${1:-$ELASTIC_IP}"
KEY="${KEY_NAME:-outreach-key}"
DOMAIN="outreach.taggiq.com"

if [ -z "$IP" ]; then
    echo "Usage: bash deploy/02-setup-server.sh <ELASTIC_IP>"
    exit 1
fi

SSH="ssh -i ~/.ssh/$KEY.pem -o StrictHostKeyChecking=no ec2-user@$IP"

echo "=== Setting up Outreach server at $IP ==="
echo ""

# Step 1: Install Docker + Docker Compose + Nginx + Certbot
echo "[1/5] Installing Docker, Nginx, and Certbot..."
$SSH << 'REMOTE'
sudo dnf update -y -q
sudo dnf install -y -q docker git nginx
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Install Docker Compose plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -sL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Install certbot
sudo dnf install -y -q python3-pip
sudo pip3 install -q certbot certbot-nginx

echo "Docker: $(docker --version)"
echo "Compose: $(docker compose version)"
echo "Nginx: $(nginx -v 2>&1)"
REMOTE

# Step 2: Clone repo
echo ""
echo "[2/5] Cloning repository..."
$SSH << 'REMOTE'
if [ -d ~/paperclip-outreach ]; then
    cd ~/paperclip-outreach && git pull
else
    git clone https://github.com/skillblendltd/paperclip-outreach.git ~/paperclip-outreach
fi
REMOTE

# Step 3: Copy .env file
echo ""
echo "[3/5] Copying .env file..."
scp -i ~/.ssh/$KEY.pem -o StrictHostKeyChecking=no \
    /Users/pinani/Documents/paperclip-outreach/.env \
    ec2-user@$IP:~/paperclip-outreach/.env

# Step 4: Set up Nginx config
echo ""
echo "[4/5] Configuring Nginx..."
$SSH << REMOTE
# Generate a strong webhook secret
WEBHOOK_SECRET=\$(openssl rand -hex 32)
echo "" >> ~/paperclip-outreach/.env
echo "TAGGIQ_WEBHOOK_SECRET=\$WEBHOOK_SECRET" >> ~/paperclip-outreach/.env
echo "Webhook secret generated and added to .env"
echo "SAVE THIS - you need to add it to TaggIQ's .env too:"
echo "  OUTREACH_WEBHOOK_SECRET=\$WEBHOOK_SECRET"

# Nginx config (HTTP first, certbot adds SSL later)
sudo tee /etc/nginx/conf.d/outreach.conf > /dev/null << 'NGINX'
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 1m;
    }
}
NGINX

sudo nginx -t && sudo systemctl restart nginx && sudo systemctl enable nginx
echo "Nginx configured for $DOMAIN"
REMOTE

# Step 5: Get SSL cert (must have DNS pointed first)
echo ""
echo "[5/5] SSL certificate..."
echo ""
echo "  IMPORTANT: Before running certbot, make sure DNS is set up:"
echo "    $DOMAIN -> $IP"
echo ""
echo "  Once DNS is ready, SSH in and run:"
echo "    ssh -i ~/.ssh/$KEY.pem ec2-user@$IP"
echo "    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m prakash@taggiq.com"
echo ""
echo "============================================"
echo "  SERVER SETUP COMPLETE"
echo "============================================"
echo ""
echo "  NEXT STEPS:"
echo "  1. Point DNS: $DOMAIN -> $IP"
echo "  2. SSH in: ssh -i ~/.ssh/$KEY.pem ec2-user@$IP"
echo "  3. Run certbot (see above)"
echo "  4. Run: bash deploy/03-migrate-and-launch.sh $IP"
echo ""
