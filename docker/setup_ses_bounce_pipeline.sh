#!/bin/bash
#
# DevOps script — set up SES bounce → SNS → SQS pipeline.
# Run this ONCE on a machine with AWS CLI credentials configured (your laptop).
#
# Prerequisites:
#   - aws CLI installed and configured: `aws configure` with an admin or
#     ses+sns+sqs+iam-capable identity
#   - Region: eu-west-1 (matches existing infra)
#
# Usage:
#   bash docker/setup_ses_bounce_pipeline.sh
#
# Idempotent: safe to re-run. Existing resources are left alone.

set -euo pipefail

REGION="eu-west-1"
CONFIG_SET="paperclip-bounces"
SNS_TOPIC="taggiq-ses-bounces"
SQS_QUEUE="taggiq-ses-bounces-queue"
IAM_USER="paperclip-bounce-poller"
IAM_POLICY="paperclip-bounce-poller-policy"

# Sending identities to attach config set to (must be already SES-verified)
SES_IDENTITIES=(
  "mail.taggiq.com"
  "mail.kritno.com"
  "mail.fullypromoted.ie"
)

echo "================================================================"
echo "Paperclip SES Bounce Pipeline Setup"
echo "Region: $REGION"
echo "================================================================"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account: $ACCOUNT_ID"
echo

# ---------------------------------------------------------------
# 1. Create SNS topic
# ---------------------------------------------------------------
echo "[1/8] Creating SNS topic '$SNS_TOPIC'..."
SNS_ARN=$(aws sns create-topic \
  --region "$REGION" \
  --name "$SNS_TOPIC" \
  --query TopicArn --output text)
echo "    SNS ARN: $SNS_ARN"

# ---------------------------------------------------------------
# 2. Create SQS queue
# ---------------------------------------------------------------
echo "[2/8] Creating SQS queue '$SQS_QUEUE'..."
SQS_URL=$(aws sqs create-queue \
  --region "$REGION" \
  --queue-name "$SQS_QUEUE" \
  --attributes "VisibilityTimeout=60,MessageRetentionPeriod=345600,ReceiveMessageWaitTimeSeconds=5" \
  --query QueueUrl --output text)
SQS_ARN=$(aws sqs get-queue-attributes \
  --region "$REGION" \
  --queue-url "$SQS_URL" \
  --attribute-names QueueArn \
  --query "Attributes.QueueArn" --output text)
echo "    SQS URL: $SQS_URL"
echo "    SQS ARN: $SQS_ARN"

# ---------------------------------------------------------------
# 3. Allow SNS to publish to SQS
# ---------------------------------------------------------------
echo "[3/8] Granting SNS → SQS publish permission..."
SQS_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowSNSPublish",
    "Effect": "Allow",
    "Principal": {"Service": "sns.amazonaws.com"},
    "Action": "sqs:SendMessage",
    "Resource": "$SQS_ARN",
    "Condition": {"ArnEquals": {"aws:SourceArn": "$SNS_ARN"}}
  }]
}
EOF
)
aws sqs set-queue-attributes \
  --region "$REGION" \
  --queue-url "$SQS_URL" \
  --attributes "Policy=$(echo "$SQS_POLICY" | tr -d '\n' | sed 's/"/\\"/g' | xargs -0 printf '%s')" \
  >/dev/null
echo "    Granted."

# ---------------------------------------------------------------
# 4. Subscribe SQS to SNS
# ---------------------------------------------------------------
echo "[4/8] Subscribing SQS to SNS topic..."
aws sns subscribe \
  --region "$REGION" \
  --topic-arn "$SNS_ARN" \
  --protocol sqs \
  --notification-endpoint "$SQS_ARN" \
  --query SubscriptionArn --output text

# ---------------------------------------------------------------
# 5. Create SES Configuration Set
# ---------------------------------------------------------------
echo "[5/8] Creating SES Configuration Set '$CONFIG_SET'..."
if aws sesv2 get-configuration-set \
    --region "$REGION" \
    --configuration-set-name "$CONFIG_SET" >/dev/null 2>&1; then
  echo "    Already exists, skipping create."
else
  aws sesv2 create-configuration-set \
    --region "$REGION" \
    --configuration-set-name "$CONFIG_SET"
  echo "    Created."
fi

# ---------------------------------------------------------------
# 6. Add Event Destination → SNS for Bounce/Complaint/Reject
# ---------------------------------------------------------------
echo "[6/8] Adding event destination → SNS for Bounce/Complaint/Reject..."
DEST_NAME="bounce-complaint-reject-to-sns"
# Idempotency: try update first, fall back to create
if aws sesv2 update-configuration-set-event-destination \
    --region "$REGION" \
    --configuration-set-name "$CONFIG_SET" \
    --event-destination-name "$DEST_NAME" \
    --event-destination "Enabled=true,MatchingEventTypes=BOUNCE,COMPLAINT,REJECT,SnsDestination={TopicArn=$SNS_ARN}" \
    >/dev/null 2>&1; then
  echo "    Updated existing event destination."
else
  aws sesv2 create-configuration-set-event-destination \
    --region "$REGION" \
    --configuration-set-name "$CONFIG_SET" \
    --event-destination-name "$DEST_NAME" \
    --event-destination "Enabled=true,MatchingEventTypes=BOUNCE,COMPLAINT,REJECT,SnsDestination={TopicArn=$SNS_ARN}"
  echo "    Created event destination."
fi

# ---------------------------------------------------------------
# 7. Note about per-identity config set defaults
# ---------------------------------------------------------------
echo "[7/8] Setting default config set on each verified domain identity..."
for IDENTITY in "${SES_IDENTITIES[@]}"; do
  echo "    -> $IDENTITY"
  if aws sesv2 put-email-identity-configuration-set-attributes \
      --region "$REGION" \
      --email-identity "$IDENTITY" \
      --configuration-set-name "$CONFIG_SET" 2>/dev/null; then
    echo "       Attached as default config set."
  else
    echo "       WARNING: identity not verified or not accessible. Skipping."
  fi
done

# ---------------------------------------------------------------
# 8. Create IAM user for the bounce-poller, with minimal SQS perms
# ---------------------------------------------------------------
echo "[8/8] Creating IAM user '$IAM_USER' with minimal SQS perms..."
if aws iam get-user --user-name "$IAM_USER" >/dev/null 2>&1; then
  echo "    User already exists."
else
  aws iam create-user --user-name "$IAM_USER" >/dev/null
  echo "    User created."
fi

POLICY_DOC=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ],
    "Resource": "$SQS_ARN"
  }]
}
EOF
)
aws iam put-user-policy \
  --user-name "$IAM_USER" \
  --policy-name "$IAM_POLICY" \
  --policy-document "$POLICY_DOC"
echo "    Inline policy applied."

# Generate access keys (only if user has none)
EXISTING_KEYS=$(aws iam list-access-keys --user-name "$IAM_USER" --query 'AccessKeyMetadata[*].AccessKeyId' --output text)
if [ -z "$EXISTING_KEYS" ]; then
  echo "    Creating access key for $IAM_USER..."
  KEY_JSON=$(aws iam create-access-key --user-name "$IAM_USER" --output json)
  AK=$(echo "$KEY_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKey']['AccessKeyId'])")
  SK=$(echo "$KEY_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKey']['SecretAccessKey'])")
  echo
  echo "    ┌──────────────────────────────────────────────────────────────┐"
  echo "    │ ACCESS KEYS — STORE THESE NOW (cannot be retrieved later)    │"
  echo "    │                                                              │"
  echo "    │ AWS_ACCESS_KEY_ID:     $AK"
  echo "    │ AWS_SECRET_ACCESS_KEY: $SK"
  echo "    │                                                              │"
  echo "    │ Add these to docker/.env on EC2 (or set in compose env_file).│"
  echo "    └──────────────────────────────────────────────────────────────┘"
else
  echo "    User already has access keys: $EXISTING_KEYS"
  echo "    To rotate: delete and re-create."
fi

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
echo
echo "================================================================"
echo "DONE. Pipeline summary:"
echo "================================================================"
echo "  SES Configuration Set : $CONFIG_SET"
echo "  SNS Topic             : $SNS_ARN"
echo "  SQS Queue URL         : $SQS_URL"
echo "  SQS Queue ARN         : $SQS_ARN"
echo "  IAM User              : $IAM_USER"
echo
echo "Add to docker/.env on EC2 (then 'docker compose up -d' to restart):"
echo
echo "  AWS_ACCESS_KEY_ID=<from above>"
echo "  AWS_SECRET_ACCESS_KEY=<from above>"
echo "  AWS_REGION=$REGION"
echo "  AWS_SES_CONFIGURATION_SET=$CONFIG_SET"
echo "  AWS_SES_BOUNCES_SQS_URL=$SQS_URL"
echo
echo "Then verify the pipeline:"
echo "  docker exec outreach_cron python manage.py process_ses_bounces --dry-run"
echo
echo "Acceptance test (sends to AWS bounce simulator):"
echo "  docker exec outreach_cron python -c \"from campaigns.email_service import EmailService; EmailService.send_email(['bounce@simulator.amazonses.com'], 'test', '<p>test</p>', from_email='prakash@mail.taggiq.com', from_name='Test')\""
echo "  # Wait 1-2 minutes"
echo "  docker exec outreach_cron python manage.py process_ses_bounces"
echo "  docker exec outreach_cron python manage.py shell -c \"from campaigns.models import Suppression; print(Suppression.objects.filter(email='bounce@simulator.amazonses.com').values('reason','notes'))\""
