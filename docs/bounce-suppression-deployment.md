# SES Bounce/Complaint Auto-Suppression - Deployment Runbook

## Overview

This deployment adds automatic suppression of bounced and complained email addresses via AWS Lambda and SNS. The system captures SES events in real-time and prevents repeated sends to bad addresses, protecting sender reputation.

## Deployment Steps

### Phase 1: Code Deployment to EC2

```bash
# SSH to EC2
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@54.220.116.228

# Pull latest code
cd /var/www/paperclip-outreach
git pull origin main

# Apply database migrations
docker exec outreach_db psql -U outreach_user -d outreach_db << 'EOF'
  -- Check if migration has been applied
  SELECT version FROM django_migrations WHERE app = 'campaigns' 
    AND name = '0028_suppression_bounce_tracking';
EOF

# Inside cron container, run migrations
docker exec outreach_cron python manage.py migrate
```

### Phase 2: AWS Infrastructure Setup

**⚠️ IMPORTANT: These steps require AWS CLI access and IAM permissions.**

#### 2a. Create SES Configuration Set

```bash
# Create Configuration Set
aws ses create-configuration-set \
    --configuration-set Name=paperclip-outreach \
    --region us-east-1

# Verify creation
aws ses list-configuration-sets --region us-east-1
```

#### 2b. Create SNS Topic

```bash
# Create topic
TOPIC_ARN=$(aws sns create-topic \
    --name paperclip-outreach-ses-events \
    --region us-east-1 \
    --query 'TopicArn' \
    --output text)

echo "Topic ARN: $TOPIC_ARN"
# Save this value - you'll need it in subsequent steps
```

#### 2c. Create Configuration Set Event Destination

```bash
TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:paperclip-outreach-ses-events"

aws ses create-configuration-set-event-destination \
    --configuration-set-name paperclip-outreach \
    --event-destination \
        Name=SESEventDestination,\
Enabled=true,\
MatchingEventTypes=Send,Bounce,Complaint,Delivery,Open,Click,\
SNSDestination={TopicARN=$TOPIC_ARN} \
    --region us-east-1

# Verify
aws ses describe-configuration-set \
    --configuration-set-name paperclip-outreach \
    --region us-east-1
```

#### 2d. Create IAM Role for Lambda

```bash
# Save trust policy
cat > /tmp/lambda-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
    --role-name paperclip-outreach-lambda-ses \
    --assume-role-policy-document file:///tmp/lambda-trust.json \
    --region us-east-1

# Attach basic execution policy
aws iam attach-role-policy \
    --role-name paperclip-outreach-lambda-ses \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

#### 2e. Package and Deploy Lambda Function

**From your local machine:**

```bash
cd /Users/pinani/Documents/paperclip-outreach

# Create deployment package
mkdir -p /tmp/lambda-deploy
cp campaigns/aws/lambda_ses_events.py /tmp/lambda-deploy/lambda_ses_events.py

# Install psycopg2 (PostgreSQL driver)
pip install psycopg2-binary -t /tmp/lambda-deploy/

# Create ZIP
cd /tmp/lambda-deploy
zip -r /tmp/lambda_function.zip .
cd -

# Get the role ARN (from previous step)
ROLE_ARN="arn:aws:iam::ACCOUNT_ID:role/paperclip-outreach-lambda-ses"

# Create Lambda function
aws lambda create-function \
    --function-name paperclip-outreach-ses-events \
    --runtime python3.12 \
    --role $ROLE_ARN \
    --handler lambda_ses_events.lambda_handler \
    --zip-file fileb:///tmp/lambda_function.zip \
    --timeout 30 \
    --memory-size 256 \
    --region us-east-1 \
    --environment 'Variables={
        DB_HOST=54.220.116.228,
        DB_NAME=outreach_db,
        DB_USER=outreach_user,
        DB_PASSWORD='<ACTUAL_PASSWORD>',
        DB_PORT=5432,
        DB_SSLMODE=allow
    }'
```

**Important:** Replace `<ACTUAL_PASSWORD>` with the actual PostgreSQL password.

#### 2f. Grant SNS Permission to Invoke Lambda

```bash
TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:paperclip-outreach-ses-events"

aws lambda add-permission \
    --function-name paperclip-outreach-ses-events \
    --statement-id AllowSNSInvoke \
    --action lambda:InvokeFunction \
    --principal sns.amazonaws.com \
    --source-arn $TOPIC_ARN \
    --region us-east-1
```

#### 2g. Subscribe Lambda to SNS Topic

```bash
TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:paperclip-outreach-ses-events"

aws sns subscribe \
    --topic-arn $TOPIC_ARN \
    --protocol lambda \
    --notification-endpoint arn:aws:lambda:us-east-1:ACCOUNT_ID:function:paperclip-outreach-ses-events \
    --region us-east-1

# Verify subscription
aws sns list-subscriptions-by-topic \
    --topic-arn $TOPIC_ARN \
    --region us-east-1
```

### Phase 3: Environment Configuration

#### 3a. Update EC2 Environment Variables

```bash
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@54.220.116.228

# Edit cron environment
sudo nano /var/www/paperclip-outreach/docker/.env.cron

# Add or update:
AWS_SES_CONFIGURATION_SET=paperclip-outreach

# Save and exit
```

#### 3b. Restart Docker Containers

```bash
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@54.220.116.228

cd /var/www/paperclip-outreach
docker compose up -d

# Verify services are running
docker compose ps

# Check logs
docker compose logs -f cron
```

### Phase 4: Verification & Testing

#### 4a. Test Configuration

```bash
# SSH to EC2
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@54.220.116.228

# Run diagnostics
docker exec outreach_cron python manage.py test_bounce_pipeline

# Expected output:
# ✓ AWS_SES_CONFIGURATION_SET: paperclip-outreach
# ✓ Suppression model fields verified
# ✓ is_suppressed function working
```

#### 4b. Test with Real Email

```bash
# Send test email to SES bounce simulator
docker exec outreach_cron python manage.py test_bounce_pipeline --send-test-email

# This will send to bounce@simulator.amazonses.com which triggers SES to send
# a bounce event. Give it 30-60 seconds to process through SNS → Lambda.

# Check for suppression
docker exec outreach_cron python manage.py test_bounce_pipeline --check-suppressions

# You should see a new hard_bounce suppression for bounce@simulator.amazonses.com
```

#### 4c. Verify Lambda Logs

```bash
# Monitor Lambda execution logs
aws logs tail /aws/lambda/paperclip-outreach-ses-events --follow --region us-east-1

# Tail for 30 seconds while test email processes
# You should see logs like:
# Processing SES event type: Bounce
# Suppressing email: bounce@simulator.amazonses.com (reason: hard_bounce)
```

#### 4d. Run Test Suite

```bash
# On EC2, run the bounce suppression tests
docker exec outreach_cron python manage.py test campaigns.tests.test_bounce_suppression -v 2

# Expected: 8 tests pass
```

### Phase 5: Live Traffic Monitoring

#### 5a. Monitor Bounce Creation

```bash
# SSH to EC2 and run this every few minutes:
docker exec outreach_cron python manage.py test_bounce_pipeline --check-suppressions

# Watch for new suppressions appearing automatically when bounces occur
```

#### 5b. CloudWatch Dashboard

```bash
# View bounce metrics from SES
aws cloudwatch get-metric-statistics \
    --namespace AWS/SES \
    --metric-name Bounce \
    --dimensions Name=Configuration Set,Value=paperclip-outreach \
    --start-time $(date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Sum \
    --region us-east-1
```

#### 5c. Monitor Campaign Sends

```bash
# Check that campaigns are using the configuration set:
docker exec outreach_cron python manage.py send_sequences --dry-run --status

# All sends should now include X-SES-CONFIGURATION-SET header
# which triggers bounce/complaint events in SES
```

## Troubleshooting

### Lambda Not Invoked

```bash
# 1. Check SNS subscription
aws sns list-subscriptions-by-topic --topic-arn $TOPIC_ARN --region us-east-1

# 2. Check Lambda permission
aws lambda get-policy --function-name paperclip-outreach-ses-events --region us-east-1

# 3. Check CloudWatch Logs
aws logs describe-log-streams \
    --log-group-name /aws/lambda/paperclip-outreach-ses-events \
    --region us-east-1
```

### Database Connection Fails

```bash
# 1. Test connection from Lambda (using AWS Lambda console)
# Go to AWS Lambda console → function → Test
# Run a test with the event:
{
  "Records": [{
    "Sns": {
      "Message": "{\"eventType\":\"Bounce\",\"bounce\":{\"bounceType\":\"Permanent\",\"bouncedRecipients\":[{\"emailAddress\":\"test@example.com\"}]}}"
    }
  }]
}

# 2. Check security group allows Lambda to EC2 port 5432
aws ec2 describe-security-groups --group-ids sg-XXXXXXXX --region us-east-1

# 3. Check database is accepting connections
docker exec outreach_db psql -U outreach_user -d outreach_db -c "SELECT 1;"
```

### Soft Bounces Not Suppressing

```bash
# Check soft bounce count is incrementing:
docker exec outreach_cron python manage.py shell << 'EOF'
from campaigns.models import Suppression
soft = Suppression.objects.filter(reason='soft_bounce').order_by('-updated_at')
for s in soft[:5]:
    print(f'{s.email}: count={s.soft_bounce_count}')
EOF

# If count isn't incrementing, check Lambda logs for errors
aws logs tail /aws/lambda/paperclip-outreach-ses-events --follow --region us-east-1
```

## Rollback Procedure

If something goes wrong:

```bash
# 1. Stop using Configuration Set (temporary)
# Update EC2 env to unset AWS_SES_CONFIGURATION_SET or set to empty
# Restart containers

# 2. Disable Lambda invocation
aws lambda delete-function \
    --function-name paperclip-outreach-ses-events \
    --region us-east-1

# 3. Verify campaigns still send (they will, just without bounce tracking)
docker exec outreach_cron python manage.py send_sequences --dry-run --status

# 4. Keep suppressions already created (don't delete the Suppression table records)
```

## Monitoring Checklist

- [ ] Lambda function deployed and permissions granted
- [ ] SNS subscription active
- [ ] Test email triggers bounce suppression within 60 seconds
- [ ] CloudWatch logs show successful Lambda invocations
- [ ] Suppression table growing as bounces occur
- [ ] is_suppressed() blocks bounced addresses from sending
- [ ] Soft bounce counter incrementing correctly
- [ ] Complaints suppressing globally (product = NULL)

## Performance Expectations

- **Bounce to suppression:** 10-30 seconds (SES → SNS → Lambda)
- **Test email to bounce:** 30-60 seconds (SES processing)
- **Lambda invocation:** <1 second
- **Database insert:** <100ms

## Cost Impact

- SES events: free
- SNS: ~$0.50 per 1M notifications
- Lambda: ~$0.20 per 1M invocations (~$1-2/month for 10k bounces)
- **Total estimated:** <$5/month

## Next Steps

1. Deploy to EC2
2. Test with real bounces
3. Monitor for 1 week
4. Adjust soft bounce threshold if needed (currently 3)
5. Add DMARC reporting (will reduce complaints significantly)
6. Implement complaint feedback analysis (which complaint type triggered it)
