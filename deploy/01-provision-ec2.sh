#!/bin/bash
# =============================================================================
# Step 1: Provision EC2 instance for Paperclip Outreach
# Run from your local machine (needs AWS CLI configured)
#
# No domain, no Nginx, no SSL. Just Docker on EC2.
# TaggIQ talks to it via private IP (same VPC).
# Vapi talks to it via public IP (Elastic IP).
# =============================================================================

set -e

REGION="eu-west-1"
INSTANCE_TYPE="t3.micro"
KEY_NAME="outreach-key"

echo "=== Paperclip Outreach EC2 Provisioning ==="
echo ""

# Step 1: Find TaggIQ's VPC and security group
echo "[1/5] Finding TaggIQ VPC..."
TAGGIQ_VPC=$(aws ec2 describe-instances \
    --filters "Name=ip-address,Values=3.252.51.180" \
    --query 'Reservations[0].Instances[0].VpcId' \
    --output text \
    --region $REGION 2>/dev/null)

if [ "$TAGGIQ_VPC" = "None" ] || [ -z "$TAGGIQ_VPC" ]; then
    echo "Could not auto-detect TaggIQ VPC. Enter manually:"
    read -p "VPC ID: " TAGGIQ_VPC
fi

TAGGIQ_SG=$(aws ec2 describe-instances \
    --filters "Name=ip-address,Values=3.252.51.180" \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
    --output text \
    --region $REGION 2>/dev/null)

echo "  VPC: $TAGGIQ_VPC"
echo "  TaggIQ SG: $TAGGIQ_SG"

# Find a public subnet
SUBNET_ID=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$TAGGIQ_VPC" "Name=map-public-ip-on-launch,Values=true" \
    --query 'Subnets[0].SubnetId' \
    --output text \
    --region $REGION)
echo "  Subnet: $SUBNET_ID"

# Step 2: Create SSH key pair
echo ""
echo "[2/5] SSH key pair..."
if aws ec2 describe-key-pairs --key-names $KEY_NAME --region $REGION &>/dev/null; then
    echo "  Key '$KEY_NAME' already exists"
else
    aws ec2 create-key-pair \
        --key-name $KEY_NAME \
        --query 'KeyMaterial' \
        --output text \
        --region $REGION > ~/.ssh/$KEY_NAME.pem
    chmod 400 ~/.ssh/$KEY_NAME.pem
    echo "  Created ~/.ssh/$KEY_NAME.pem"
fi

# Step 3: Create security group
echo ""
echo "[3/5] Security group..."
OUTREACH_SG=$(aws ec2 create-security-group \
    --group-name outreach-sg \
    --description "Paperclip Outreach" \
    --vpc-id $TAGGIQ_VPC \
    --query 'GroupId' \
    --output text \
    --region $REGION 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=outreach-sg" "Name=vpc-id,Values=$TAGGIQ_VPC" \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region $REGION)
echo "  Outreach SG: $OUTREACH_SG"

MY_IP=$(curl -s https://checkip.amazonaws.com)/32

# SSH from your IP
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG --protocol tcp --port 22 \
    --cidr $MY_IP --region $REGION 2>/dev/null || true

# Port 8002 from TaggIQ SG (private VPC traffic - webhooks)
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG --protocol tcp --port 8002 \
    --source-group $TAGGIQ_SG --region $REGION 2>/dev/null || true

# Port 8002 from Vapi IPs (call webhooks)
# Vapi uses Twilio infrastructure - allow broadly for now, HMAC verifies authenticity
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG --protocol tcp --port 8002 \
    --cidr 0.0.0.0/0 --region $REGION 2>/dev/null || true

echo "  Rules: SSH(your IP) + 8002(TaggIQ SG + Vapi)"

# Step 4: Get latest Amazon Linux 2023 AMI
echo ""
echo "[4/5] Launching EC2..."
AMI_ID=$(aws ec2 describe-images \
    --owners amazon \
    --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text \
    --region $REGION)

INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-group-ids $OUTREACH_SG \
    --subnet-id $SUBNET_ID \
    --associate-public-ip-address \
    --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=outreach-server}]" \
    --query 'Instances[0].InstanceId' \
    --output text \
    --region $REGION)
echo "  Instance: $INSTANCE_ID"

echo "  Waiting for running state..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

# Step 5: Allocate Elastic IP (needed for Vapi webhook callback)
echo ""
echo "[5/5] Elastic IP..."
ALLOC_ID=$(aws ec2 allocate-address \
    --domain vpc \
    --query 'AllocationId' \
    --output text \
    --region $REGION)
ELASTIC_IP=$(aws ec2 describe-addresses \
    --allocation-ids $ALLOC_ID \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region $REGION)
aws ec2 associate-address \
    --instance-id $INSTANCE_ID \
    --allocation-id $ALLOC_ID \
    --region $REGION >/dev/null

# Get private IP for TaggIQ integration
PRIVATE_IP=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
    --output text \
    --region $REGION)

echo ""
echo "============================================"
echo "  EC2 PROVISIONED"
echo "============================================"
echo ""
echo "  Instance:   $INSTANCE_ID"
echo "  Elastic IP: $ELASTIC_IP"
echo "  Private IP: $PRIVATE_IP"
echo ""
echo "  SSH: ssh -i ~/.ssh/$KEY_NAME.pem ec2-user@$ELASTIC_IP"
echo ""
echo "  TaggIQ webhook URL (add to TaggIQ .env):"
echo "    OUTREACH_WEBHOOK_URL=http://$PRIVATE_IP:8002/api/webhooks/taggiq/"
echo ""
echo "  Vapi webhook URL (update in Vapi dashboard):"
echo "    http://$ELASTIC_IP:8002/api/webhooks/vapi/"
echo ""
echo "  NEXT: bash deploy/02-setup-and-launch.sh $ELASTIC_IP"
echo ""

# Save config
cat > deploy/.ec2-config << EOF
ELASTIC_IP=$ELASTIC_IP
PRIVATE_IP=$PRIVATE_IP
INSTANCE_ID=$INSTANCE_ID
OUTREACH_SG=$OUTREACH_SG
TAGGIQ_SG=$TAGGIQ_SG
KEY_NAME=$KEY_NAME
REGION=$REGION
EOF
