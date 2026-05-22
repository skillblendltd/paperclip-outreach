# SES Bounce & Complaint Auto-Suppression Setup

This document covers the complete setup for capturing SES bounce and complaint events and auto-suppressing email addresses.

## Architecture

```
AWS SES
  ↓
Configuration Set (paperclip-outreach)
  ↓
Event Publishing (Bounce, Complaint)
  ↓
SNS Topic (paperclip-outreach-ses-events)
  ↓
Lambda Function (handle-ses-events)
  ↓
PostgreSQL Suppression Table
```

## Prerequisites

- AWS account with SES in production mode
- EC2 instance running PostgreSQL
- Lambda execution role with RDS access
- AWS CLI configured

## Step 1: Create SES Configuration Set

```bash
aws ses create-configuration-set \
    --configuration-set Name=paperclip-outreach \
    --region us-east-1
```

Verify:
```bash
aws ses list-configuration-sets --region us-east-1
```

## Step 2: Create SNS Topic

```bash
TOPIC_ARN=$(aws sns create-topic \
    --name paperclip-outreach-ses-events \
    --region us-east-1 \
    --query 'TopicArn' \
    --output text)

echo "Topic ARN: $TOPIC_ARN"
```

## Step 3: Create Event Destination (Bounce)

Link SES Configuration Set to SNS for bounce events:

```bash
TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:paperclip-outreach-ses-events"

aws ses create-configuration-set-event-destination \
    --configuration-set-name paperclip-outreach \
    --event-destination Name=BounceDestination,Enabled=true,\
MatchingEventTypes=Send,Bounce,Complaint,Delivery,Open,Click,\
RenderedFailurePlacement=HeaderBodyTuple,\
SNSDestination={TopicARN=$TOPIC_ARN} \
    --region us-east-1
```

Verify:
```bash
aws ses describe-configuration-set \
    --configuration-set-name paperclip-outreach \
    --region us-east-1
```

## Step 4: Create Lambda Function

### 4a. Create IAM Role for Lambda

```bash
# Create trust policy file
cat > /tmp/lambda-trust-policy.json << 'EOF'
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

# Create the role
ROLE_NAME="paperclip-outreach-lambda-ses"
ROLE_ARN=$(aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document file:///tmp/lambda-trust-policy.json \
    --query 'Role.Arn' \
    --output text)

echo "Role ARN: $ROLE_ARN"

# Attach basic Lambda execution policy
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Attach RDS access policy (or create custom)
cat > /tmp/lambda-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeNetworkInterfaces",
        "ec2:CreateNetworkInterface",
        "ec2:DeleteNetworkInterface"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name paperclip-outreach-lambda-policy \
    --policy-document file:///tmp/lambda-policy.json
```

### 4b. Package Lambda Function

```bash
cd /Users/pinani/Documents/paperclip-outreach

# Create deployment package
mkdir -p /tmp/lambda-package
cp campaigns/aws/lambda_ses_events.py /tmp/lambda-package/

# Install psycopg2 for PostgreSQL
pip install psycopg2-binary -t /tmp/lambda-package/

# Create ZIP
cd /tmp/lambda-package
zip -r /tmp/lambda_function.zip .
```

### 4c. Create Lambda Function

```bash
ROLE_ARN="arn:aws:iam::ACCOUNT_ID:role/paperclip-outreach-lambda-ses"

FUNCTION_ARN=$(aws lambda create-function \
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
        DB_PASSWORD=<FROM_SECRETS_MANAGER>,
        DB_PORT=5432
    }' \
    --query 'FunctionArn' \
    --output text)

echo "Function ARN: $FUNCTION_ARN"
```

**Important:** Replace DB_PASSWORD with actual value from AWS Secrets Manager or EC2 environment.

### 4d. Allow SNS to Invoke Lambda

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

## Step 5: Subscribe Lambda to SNS

```bash
TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:paperclip-outreach-ses-events"
FUNCTION_ARN="arn:aws:lambda:us-east-1:ACCOUNT_ID:function:paperclip-outreach-ses-events"

aws sns subscribe \
    --topic-arn $TOPIC_ARN \
    --protocol lambda \
    --notification-endpoint $FUNCTION_ARN \
    --region us-east-1
```

Verify:
```bash
aws sns list-subscriptions-by-topic \
    --topic-arn $TOPIC_ARN \
    --region us-east-1
```

## Step 6: Update Django Settings

Add to environment variables on EC2:

```bash
export AWS_SES_CONFIGURATION_SET=paperclip-outreach
```

In `docker/.env.cron` or `docker-compose.yml`:

```yaml
environment:
  - AWS_SES_CONFIGURATION_SET=paperclip-outreach
```

## Step 7: Deploy Code Changes

```bash
cd /Users/pinani/Documents/paperclip-outreach

# Apply migrations
python manage.py migrate

# Test that Suppression model changes are applied
python manage.py shell << 'EOF'
from campaigns.models import Suppression
print(Suppression.REASON_CHOICES)
EOF
```

## Step 8: Test the Pipeline

### 8a. Create a test suppression

```bash
python manage.py shell << 'EOF'
from campaigns.models import Suppression, Product
from campaigns.utils import is_likely_test_email

# Get a product
product = Product.objects.first()

# Create a test suppression
supp, created = Suppression.objects.get_or_create(
    email='bounce-test@example.com',
    product=product,
    defaults={'reason': 'hard_bounce', 'notes': 'Manual test'}
)
print(f'Created: {created}, Email: {supp.email}, Reason: {supp.reason}')
EOF
```

### 8b. Send a test email to trigger bounce

Use SES sandbox or send to an address that bounces:

```bash
python manage.py shell << 'EOF'
from campaigns.email_service import EmailService
from django.conf import settings

result = EmailService.send_email(
    to_emails=['bounce@simulator.amazonses.com'],  # SES simulator
    subject='Test bounce',
    body_html='<p>This email will bounce</p>',
    from_email=settings.AWS_SES_FROM_EMAIL,
)
print(f'Result: {result}')
EOF
```

### 8c. Monitor Lambda Logs

```bash
aws logs tail /aws/lambda/paperclip-outreach-ses-events --follow --region us-east-1
```

### 8d. Verify Suppression Created

```bash
python manage.py shell << 'EOF'
from campaigns.models import Suppression

suppressed = Suppression.objects.filter(reason='hard_bounce').order_by('-created_at')
for s in suppressed[:5]:
    print(f'{s.email} - {s.reason} - {s.notes}')
EOF
```

## Troubleshooting

### Lambda not being invoked

1. Check SNS subscription exists:
   ```bash
   aws sns list-subscriptions-by-topic --topic-arn $TOPIC_ARN
   ```

2. Check Lambda permission:
   ```bash
   aws lambda get-policy --function-name paperclip-outreach-ses-events
   ```

3. Test SNS → Lambda manually:
   ```bash
   aws sns publish \
       --topic-arn $TOPIC_ARN \
       --message '{"eventType":"Bounce","bounce":{"bounceType":"Permanent","bouncedRecipients":[{"emailAddress":"test@example.com"}]}}'
   ```

### Database connection errors

1. Check VPC security group allows Lambda to reach RDS:
   ```bash
   # Lambda needs egress on port 5432 to RDS
   aws ec2 describe-security-groups --region us-east-1
   ```

2. Verify environment variables:
   ```bash
   aws lambda get-function-configuration \
       --function-name paperclip-outreach-ses-events \
       --region us-east-1 \
       | grep Environment
   ```

3. Test connection:
   ```bash
   python manage.py shell << 'EOF'
   import psycopg2
   conn = psycopg2.connect(
       host='54.220.116.228',
       database='outreach_db',
       user='outreach_user',
       password='<password>',
       port=5432
   )
   print('Connected OK')
   conn.close()
   EOF
   ```

### Soft bounces not being suppressed after 3 attempts

1. Verify soft bounce counter is incrementing:
   ```bash
   python manage.py shell << 'EOF'
   from campaigns.models import Suppression
   
   soft_bounces = Suppression.objects.filter(reason='soft_bounce')
   for s in soft_bounces.order_by('-updated_at')[:10]:
       print(f'{s.email} - count: {s.soft_bounce_count} - {s.updated_at}')
   EOF
   ```

2. Check Lambda logs for increment operation success:
   ```bash
   aws logs filter-log-events \
       --log-group-name /aws/lambda/paperclip-outreach-ses-events \
       --filter-pattern "soft bounce" \
       --region us-east-1
   ```

## Monitoring Dashboard

Create a CloudWatch dashboard to monitor bounce/complaint events:

```bash
# View SES metrics
aws cloudwatch get-metric-statistics \
    --namespace AWS/SES \
    --metric-name Bounce \
    --dimensions Name=Configuration Set,Value=paperclip-outreach \
    --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Sum \
    --region us-east-1
```

## Cost Implications

- **SES Events:** Free (included with SES)
- **SNS:** $0.50 per million SNS requests
- **Lambda:** ~$0.20 per 1 million invocations + compute time
- **CloudWatch Logs:** ~$0.50 per GB

Estimated monthly cost: <$5 for typical volume (10k+ bounces/month).

## Security Considerations

1. **Database credentials:** Store in AWS Secrets Manager, not environment variables
2. **Lambda VPC:** Consider running Lambda in same VPC as RDS for security
3. **SNS topic:** Add resource-based policy to restrict who can publish
4. **Email validation:** Implement DMARC, SPF, DKIM to reduce bounces

## Deployment Checklist

- [ ] SES Configuration Set created
- [ ] SNS topic created
- [ ] Event destination configured
- [ ] Lambda function deployed
- [ ] Lambda permissions granted
- [ ] SNS subscription active
- [ ] Django migrations applied
- [ ] AWS_SES_CONFIGURATION_SET environment variable set
- [ ] Test email sent and bounce captured
- [ ] Suppression record created automatically
- [ ] CloudWatch logs showing successful Lambda invocations

## Next Steps

1. **Monitor bounce rates** - Track Suppression table growth
2. **Tune soft bounce threshold** - Currently 3, adjust if needed
3. **Implement DMARC** - Will reduce complaint rate significantly
4. **Add complaint feedback loop** - Store complaint type and reason
5. **Analytics dashboard** - Track bounce vs complaint vs hard bounce trends
