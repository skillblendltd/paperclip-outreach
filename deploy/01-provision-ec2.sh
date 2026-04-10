#!/bin/bash
# =============================================================================
# Step 1: Provision EC2 instance for Paperclip Outreach
# Run this from your local machine (needs AWS CLI configured)
#
# Prerequisites:
#   - AWS CLI installed and configured (aws configure)
#   - Your TaggIQ VPC ID (check AWS console)
# =============================================================================

set -e

REGION="eu-west-1"
INSTANCE_TYPE="t3.micro"
KEY_NAME="outreach-key"
AMI_ID="ami-0694d931cee176e7d"  # Amazon Linux 2023 in eu-west-1 (update if needed)

echo "=== Paperclip Outreach EC2 Provisioning ==="
echo ""

# Step 1: Get the VPC ID from TaggIQ's EC2 instance
echo "[1/6] Finding TaggIQ VPC..."
TAGGIQ_VPC=$(aws ec2 describe-instances \
    --filters "Name=ip-address,Values=3.252.51.180" \
    --query 'Reservations[0].Instances[0].VpcId' \
    --output text \
    --region $REGION 2>/dev/null)

if [ "$TAGGIQ_VPC" = "None" ] || [ -z "$TAGGIQ_VPC" ]; then
    echo "ERROR: Could not find TaggIQ EC2. Enter VPC ID manually:"
    read -p "VPC ID: " TAGGIQ_VPC
fi
echo "  VPC: $TAGGIQ_VPC"

# Step 2: Get TaggIQ's security group
TAGGIQ_SG=$(aws ec2 describe-instances \
    --filters "Name=ip-address,Values=3.252.51.180" \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
    --output text \
    --region $REGION 2>/dev/null)
echo "  TaggIQ SG: $TAGGIQ_SG"

# Step 3: Get a public subnet in the same VPC
SUBNET_ID=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$TAGGIQ_VPC" "Name=map-public-ip-on-launch,Values=true" \
    --query 'Subnets[0].SubnetId' \
    --output text \
    --region $REGION)
echo "  Subnet: $SUBNET_ID"

# Step 4: Create SSH key pair (if it doesn't exist)
echo ""
echo "[2/6] Creating SSH key pair..."
if aws ec2 describe-key-pairs --key-names $KEY_NAME --region $REGION 2>/dev/null; then
    echo "  Key pair '$KEY_NAME' already exists"
else
    aws ec2 create-key-pair \
        --key-name $KEY_NAME \
        --query 'KeyMaterial' \
        --output text \
        --region $REGION > ~/.ssh/$KEY_NAME.pem
    chmod 400 ~/.ssh/$KEY_NAME.pem
    echo "  Created ~/.ssh/$KEY_NAME.pem"
fi

# Step 5: Create security group
echo ""
echo "[3/6] Creating security group..."
OUTREACH_SG=$(aws ec2 create-security-group \
    --group-name outreach-sg \
    --description "Paperclip Outreach - webhook receiver + admin" \
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

# Get your public IP for SSH access
MY_IP=$(curl -s https://checkip.amazonaws.com)/32
echo "  Your IP: $MY_IP"

# SSH from your IP
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG \
    --protocol tcp --port 22 \
    --cidr $MY_IP \
    --region $REGION 2>/dev/null || true

# HTTPS from TaggIQ SG (webhooks)
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG \
    --protocol tcp --port 443 \
    --source-group $TAGGIQ_SG \
    --region $REGION 2>/dev/null || true

# HTTPS from your IP (admin access)
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG \
    --protocol tcp --port 443 \
    --cidr $MY_IP \
    --region $REGION 2>/dev/null || true

# HTTP for Let's Encrypt cert validation
aws ec2 authorize-security-group-ingress \
    --group-id $OUTREACH_SG \
    --protocol tcp --port 80 \
    --cidr 0.0.0.0/0 \
    --region $REGION 2>/dev/null || true

echo "  Security group rules configured"

# Step 6: Launch EC2 instance
echo ""
echo "[4/6] Launching EC2 instance..."
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

echo ""
echo "[5/6] Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

# Step 7: Allocate and associate Elastic IP
echo ""
echo "[6/6] Allocating Elastic IP..."
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
    --region $REGION

echo ""
echo "============================================"
echo "  EC2 PROVISIONED SUCCESSFULLY"
echo "============================================"
echo ""
echo "  Instance ID: $INSTANCE_ID"
echo "  Elastic IP:  $ELASTIC_IP"
echo "  SSH key:     ~/.ssh/$KEY_NAME.pem"
echo "  SG:          $OUTREACH_SG"
echo ""
echo "  SSH:  ssh -i ~/.ssh/$KEY_NAME.pem ec2-user@$ELASTIC_IP"
echo ""
echo "  NEXT STEPS:"
echo "  1. Add DNS: outreach.taggiq.com -> $ELASTIC_IP"
echo "  2. Run: bash deploy/02-setup-server.sh $ELASTIC_IP"
echo ""

# Save config for next script
cat > deploy/.ec2-config << EOF
ELASTIC_IP=$ELASTIC_IP
INSTANCE_ID=$INSTANCE_ID
OUTREACH_SG=$OUTREACH_SG
KEY_NAME=$KEY_NAME
REGION=$REGION
EOF
echo "  Config saved to deploy/.ec2-config"
