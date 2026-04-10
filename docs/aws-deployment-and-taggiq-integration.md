# AWS Deployment + TaggIQ Integration Plan

**Created:** 2026-04-10
**Status:** Approved
**Owner:** Prakash
**Prerequisites:** Sprint 4 (Docker + PostgreSQL migration) completed locally
**Reference:** docs/sprint-plan.md, docs/architecture-v2-plan.md

---

## What This Plan Covers

Two connected workstreams:

1. **Deploy Paperclip Outreach to AWS** - move from Prakash's local Mac to an EC2 instance in the same VPC as TaggIQ
2. **Build the TaggIQ <-> Paperclip webhook bridge** - so TaggIQ trial lifecycle events trigger automated nurture sequences in Paperclip

**Why now:** The 100-customer plan depends on converting trials at 25%. Without lifecycle automation between TaggIQ (where trials happen) and Paperclip (where email sequences run), there's zero automated touchpoints between signup and payment. This bridge closes that gap.

**Why AWS:** Both systems in the same VPC means private-IP communication, no tunnels, no ngrok, no split-brain. The Docker stack already works locally - same `docker-compose.yml` runs on EC2.

---

## Impact on Current Campaigns

### What's running today (local Mac)

| Component | How it runs | What it does |
|---|---|---|
| macOS crontab `0 11 * * 1-5` | `run_campaigns.sh` | Sends all due email sequences daily at 11am |
| macOS crontab `*/10 * * * *` | `run_reply_monitor.sh` | IMAP check + Claude auto-reply every 10 min |
| macOS crontab `0 23 * * *` | `backup_to_gdrive.sh` | Nightly DB backup to Google Drive |
| SQLite database | `db.sqlite3` (or Docker PostgreSQL after Sprint 4) | All prospect data, email logs, templates |
| Vapi webhook | `POST http://localhost:8002/api/webhooks/vapi/` | Call outcome processing (not publicly reachable) |

### Active campaign state at migration time

- 13 campaigns across TaggIQ + FP
- ~4,000 prospects in various sequence stages (seq 1 through seq 5)
- 102 email templates in DB
- ~10,000+ EmailLog records tracking what's been sent
- InboundEmail records with reply history
- Suppression records (product-scoped opt-outs)

### Migration risk assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Double-sending during switchover | HIGH | Hard cutoff: stop local cron BEFORE starting AWS cron. Never run both. |
| Lost emails during gap | LOW | Max gap is 30 min. 7-day sequence spacing means no prospect misses a sequence. |
| Stale data on AWS | MEDIUM | Dump database AFTER stopping local cron. No writes happen during transfer. |
| IMAP credentials rejected from new IP | LOW | Both Zoho and Google Workspace work from any IP with app passwords. |
| SES sending from new IP | NONE | SES uses IAM credentials, not IP-based auth. Works from anywhere. |
| Prospect sequences disrupted | NONE | Sequence logic uses `last_emailed_at` timestamps from EmailLog. All timestamps migrate with the data. |
| Reply threading broken | NONE | Message-ID and In-Reply-To headers are in EmailLog. Threading continues on AWS. |

### The guarantee

**Zero impact on current campaigns.** The sequence engine (`send_sequences`) uses database timestamps to determine eligibility. As long as the database migrates completely, every prospect picks up exactly where they left off. A prospect who received seq 3 yesterday will get seq 4 in 7 days - regardless of whether the sender is on a Mac or EC2.

---

## Architecture

### Target state

```
                          AWS eu-west-1 (same VPC)
                          
 ┌──────────────────────────────────┐    ┌─────────────────────────────────────┐
 │  TaggIQ EC2 (t3.small)          │    │  Paperclip EC2 (t3.micro)          │
 │  Private IP: 172.31.48.72       │    │  Private IP: 172.31.x.x (new)     │
 │                                  │    │                                     │
 │  Django + Celery + Redis         │    │  Docker Compose:                   │
 │  api.taggiq.com                  │    │    postgres (5432)                 │
 │                                  │    │    web (8002)                      │
 │                                  │    │    cron (send_sequences,           │
 │  Fires webhooks on:              │    │          handle_replies,           │
 │    trial_started          ───────────>│          backup)                   │
 │    supplier_connected     ───────────>│                                     │
 │    first_quote_created    ───────────>│  Nginx (443) -> localhost:8002     │
 │    trial_expiring         ───────────>│  outreach.taggiq.com              │
 │    subscription_started   ───────────>│                                     │
 │    trial_expired          ───────────>│  POST /api/webhooks/taggiq/       │
 │                                  │    │    -> verify HMAC signature        │
 │  RDS PostgreSQL                  │    │    -> create/update prospect       │
 │  taggiq-db.c58g...rds...        │    │    -> trigger lifecycle sequence   │
 │                                  │    │                                     │
 │  SG: taggiq-backend-sg          │    │  SG: outreach-sg                  │
 └──────────────────────────────────┘    └─────────────────────────────────────┘
          │                                        │
          └────────── Private subnet ──────────────┘
                    (no internet hop)
```

### External services (unchanged)

```
AWS SES (us-east-1)         <- Paperclip sends campaign emails
Zoho IMAP (imappro.zoho.eu) <- Paperclip monitors TaggIQ replies
Google IMAP                  <- Paperclip monitors FP replies
Vapi.ai                      <- Paperclip places/receives calls
Google Drive (rclone)        <- Nightly backups
```

### Cost estimate

| Resource | Monthly |
|---|---|
| EC2 t3.micro (Paperclip) | ~$8.50 |
| EBS 20GB gp3 (root volume) | ~$1.60 |
| Data transfer (same VPC, private IP) | $0 |
| Route53 A record | $0.50 |
| SSL (Let's Encrypt) | $0 |
| **Total** | **~$10.60/month** |

---

## Sprint 5: AWS Deployment (After Sprint 4)

**Prerequisite:** Sprint 4 complete - Paperclip running in Docker with PostgreSQL locally, verified for 2+ business days.

### Phase 5A: Provision AWS Infrastructure

| # | Task | Size | Notes |
|---|---|---|---|
| 5A.1 | Launch EC2 t3.micro in eu-west-1 | S | Same VPC as TaggIQ. Amazon Linux 2023 or Ubuntu 22.04. Key pair: `outreach-key`. |
| 5A.2 | Create security group `outreach-sg` | S | See security group rules below. |
| 5A.3 | Allocate Elastic IP | S | Static IP for DNS. Prevents IP change on reboot. |
| 5A.4 | Install Docker + docker-compose on EC2 | S | `sudo yum install docker` or apt equivalent. |
| 5A.5 | DNS: `outreach.taggiq.com` A record to Elastic IP | S | Route53 or wherever taggiq.com DNS is managed. |
| 5A.6 | Install Nginx + certbot on EC2 host | S | Reverse proxy with Let's Encrypt SSL. |

**Security group rules (`outreach-sg`):**

| Type | Port | Source | Purpose |
|---|---|---|---|
| SSH | 22 | Prakash's IP only | Admin access |
| HTTPS | 443 | `taggiq-backend-sg` (SG reference) | TaggIQ webhooks via private network |
| HTTPS | 443 | Vapi IP ranges | Call webhooks |
| HTTPS | 443 | Prakash's IP | Admin/API access |
| All outbound | All | 0.0.0.0/0 | SES, IMAP, Vapi API, Google Drive |

### Phase 5B: Deploy Paperclip to AWS

| # | Task | Size | Notes |
|---|---|---|---|
| 5B.1 | Clone repo on EC2 | S | `git clone` from GitHub `skillblendltd/paperclip-outreach` |
| 5B.2 | Copy `.env` to EC2 | S | `scp .env outreach-ec2:~/paperclip-outreach/` |
| 5B.3 | `docker compose up -d postgres` | S | Start PostgreSQL, verify healthy |
| 5B.4 | Verify with empty DB first | S | `docker compose up web` - confirm Django starts, migrations run |
| 5B.5 | Stop web, prepare for data migration | S | Empty DB confirmed working, now load real data |

### Phase 5C: Data Migration (The Critical Path)

This is the zero-downtime switchover procedure. Total downtime: ~30 minutes.

```
Timeline:
  T+0     Stop local cron (prevent new sends/replies)
  T+1     Dump local PostgreSQL
  T+5     Transfer dump to AWS (scp)
  T+10    Restore on AWS PostgreSQL
  T+15    Verify data integrity
  T+20    Start AWS Docker stack
  T+25    Verify with --dry-run
  T+30    Enable AWS cron - system is live
```

| # | Task | Size | Notes |
|---|---|---|---|
| 5C.1 | **STOP local cron** | S | `crontab -e` - comment out all 3 Paperclip jobs. This is the point of no return for the old system. |
| 5C.2 | Wait for any running jobs to finish | S | Check lock files: `/tmp/campaigns_daily.lock`, `/tmp/outreach_reply_monitor.lock` |
| 5C.3 | Dump local PostgreSQL | S | `docker exec outreach_db pg_dump -U outreach -d outreach > outreach_migration.sql` |
| 5C.4 | Transfer dump to AWS | S | `scp outreach_migration.sql ec2-user@<ELASTIC_IP>:~/` |
| 5C.5 | Restore on AWS | S | `docker exec -i outreach_db psql -U outreach -d outreach < outreach_migration.sql` |
| 5C.6 | Verify row counts | M | Run verification script (see below) |
| 5C.7 | `docker compose up -d` (all services) | S | Start web + cron containers |
| 5C.8 | Verify with dry-run | S | `docker exec outreach_web python manage.py send_sequences --dry-run --status` |
| 5C.9 | Verify reply monitoring | S | `docker exec outreach_web python manage.py handle_replies --dry-run` |
| 5C.10 | Check Nginx + SSL | S | `curl https://outreach.taggiq.com/api/status/` |
| 5C.11 | Update Vapi webhook URL | S | Vapi dashboard: change webhook to `https://outreach.taggiq.com/api/webhooks/vapi/` |

**Data verification script (run on AWS after restore):**

```bash
docker exec outreach_web python manage.py shell -c "
from campaigns.models import *
print('=== Data Verification ===')
print(f'Organizations: {Organization.objects.count()}')
print(f'Products: {Product.objects.count()}')
print(f'Campaigns: {Campaign.objects.count()}')
print(f'Prospects: {Prospect.objects.count()}')
print(f'EmailTemplates: {EmailTemplate.objects.count()}')
print(f'EmailLog: {EmailLog.objects.count()}')
print(f'InboundEmail: {InboundEmail.objects.count()}')
print(f'Suppressions: {Suppression.objects.count()}')
print(f'MailboxConfig: {MailboxConfig.objects.count()}')
print(f'CallLog: {CallLog.objects.count()}')
print(f'CallScript: {CallScript.objects.count()}')
print(f'PromptTemplate: {PromptTemplate.objects.count()}')
print(f'AIUsageLog: {AIUsageLog.objects.count()}')
# Check critical campaign data
for c in Campaign.objects.all().order_by('name'):
    total = c.prospect_set.count()
    sent = EmailLog.objects.filter(campaign=c, status='sent').count()
    print(f'  {c.name}: {total} prospects, {sent} emails sent')
"
```

Compare these numbers against local before proceeding. Every number must match.

### Phase 5D: Post-Migration Verification (Day 1-3)

| # | Task | Size | Notes |
|---|---|---|---|
| 5D.1 | Monitor first automated send (next 11am weekday) | M | Check `/tmp/campaigns_daily.log` inside container: `docker exec outreach_cron cat /tmp/campaigns_daily.log` |
| 5D.2 | Monitor reply handling | M | Trigger a test reply or wait for organic reply. Check `/tmp/outreach_reply_monitor.log` |
| 5D.3 | Verify backup runs | S | Check nightly backup at 23:00 (see backup section below) |
| 5D.4 | Compare send counts with pre-migration daily averages | S | Same volume = healthy. Spike or zero = investigate. |
| 5D.5 | Keep local Docker stack as cold standby for 7 days | S | Don't delete anything. Just leave cron disabled. |

### Rollback procedure

If anything goes wrong on AWS:

1. Stop AWS cron: `docker exec outreach_cron crontab -r`
2. Re-enable local cron: uncomment the 3 jobs in `crontab -e`
3. Local system resumes within 1 minute
4. Data gap: any emails sent from AWS won't be in local DB. Export EmailLog from AWS if needed.

The local PostgreSQL database is untouched during migration (we dump, not move). It serves as a 7-day safety net.

---

## Sprint 6: TaggIQ Webhook Bridge

**Prerequisite:** Sprint 5 complete - Paperclip running on AWS, verified for 2+ business days.

### Phase 6A: Paperclip Side (Receive Webhooks)

#### New model: WebhookEvent

```python
# campaigns/models.py

class WebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webhook_events'
        indexes = [
            models.Index(fields=['event_type', 'processed']),
        ]

    def __str__(self):
        return f'{self.event_type} ({self.delivery_id[:8]})'
```

#### New fields on Prospect

```python
# Add to Prospect model
taggiq_user_id = models.IntegerField(null=True, blank=True, db_index=True)
trial_started_at = models.DateTimeField(null=True, blank=True)
trial_expires_at = models.DateTimeField(null=True, blank=True)
```

#### New endpoint: POST /api/webhooks/taggiq/

```python
# campaigns/views.py

import hmac
import hashlib

@csrf_exempt
def taggiq_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # 1. Verify HMAC signature
    signature = request.headers.get('X-TaggIQ-Signature', '')
    secret = settings.TAGGIQ_WEBHOOK_SECRET
    expected = 'sha256=' + hmac.new(
        secret.encode(), request.body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        return JsonResponse({'error': 'Invalid signature'}, status=401)

    # 2. Parse payload
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # 3. Idempotency check
    delivery_id = request.headers.get('X-TaggIQ-Delivery', '')
    if not delivery_id:
        return JsonResponse({'error': 'Missing delivery ID'}, status=400)

    if WebhookEvent.objects.filter(delivery_id=delivery_id).exists():
        return JsonResponse({'status': 'already_processed'})

    # 4. Log the event
    event = WebhookEvent.objects.create(
        delivery_id=delivery_id,
        event_type=data.get('event', 'unknown'),
        payload=data,
    )

    # 5. Process the event
    try:
        _handle_taggiq_event(event)
        event.processed = True
        event.save()
    except Exception as e:
        event.error = str(e)
        event.save()
        logger.error(f'Webhook processing failed: {e}', exc_info=True)

    return JsonResponse({'status': 'ok', 'delivery_id': delivery_id})
```

#### Event handler logic

```python
def _handle_taggiq_event(event):
    data = event.payload.get('data', {})
    email = data.get('email', '').lower()
    event_type = event.event_type

    if event_type == 'trial_started':
        _handle_trial_started(data, email)

    elif event_type == 'supplier_connected':
        _handle_supplier_connected(data, email)

    elif event_type == 'first_quote_created':
        _handle_first_quote_created(data, email)

    elif event_type == 'trial_expiring':
        _handle_trial_expiring(data, email)

    elif event_type == 'subscription_started':
        _handle_subscription_started(data, email)

    elif event_type == 'trial_expired':
        _handle_trial_expired(data, email)
```

**Event actions:**

| Event | Action |
|---|---|
| `trial_started` | Find or create prospect in "TaggIQ Trial Activation" campaign. Set `status='new'`, `taggiq_user_id`, `trial_started_at`, `trial_expires_at`. If prospect exists in a cold outreach campaign, update notes but don't move them. |
| `supplier_connected` | Find prospect by email. Add note. If in activation campaign and `emails_sent < 3`, set `send_enabled=False` (they're engaged, stop nudging). |
| `first_quote_created` | Find prospect. Update status to `engaged`. Move to "TaggIQ Trial Conversion" campaign (create new prospect record, disable old one). |
| `trial_expiring` | Find prospect. If status not in (`demo_scheduled`, `design_partner`) and no subscription, create prospect in "TaggIQ Trial Expiry" campaign for urgency sequence. |
| `subscription_started` | Find prospect across all campaigns. Set `send_enabled=False` everywhere. Update status to `customer` (new status). Log the plan and MRR in notes. |
| `trial_expired` | Find prospect. If not paid, create in "TaggIQ Win-Back" campaign for re-engagement sequence. |

**Important: prospect lookup order:**
1. Match by `taggiq_user_id` (set on `trial_started`)
2. Fall back to email match across all TaggIQ campaigns
3. If no match, create new prospect (trial came from organic signup, not outbound)

### Phase 6B: TaggIQ Side (Fire Webhooks)

#### New Celery task

```python
# In TaggIQ: core/tasks.py

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fire_outreach_webhook(self, event_type, data):
    """Fire lifecycle webhook to Paperclip Outreach."""
    import hmac, hashlib, json, uuid
    from django.conf import settings
    from django.utils.timezone import now
    import requests

    url = settings.OUTREACH_WEBHOOK_URL
    secret = settings.OUTREACH_WEBHOOK_SECRET

    if not url or not secret:
        return  # Outreach integration not configured

    delivery_id = str(uuid.uuid4())
    body = json.dumps({
        'event': event_type,
        'timestamp': now().isoformat(),
        'data': data,
    })
    signature = 'sha256=' + hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    try:
        response = requests.post(url, data=body, headers={
            'Content-Type': 'application/json',
            'X-TaggIQ-Signature': signature,
            'X-TaggIQ-Event': event_type,
            'X-TaggIQ-Delivery': delivery_id,
        }, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

#### Signal hooks in TaggIQ

These fire webhooks on key lifecycle moments. The exact signal locations depend on TaggIQ's model structure, but the pattern is:

```python
# In TaggIQ: core/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from core.tasks import fire_outreach_webhook

# 1. Trial started - when a new Organization is created (user signs up)
@receiver(post_save, sender=Organization)
def on_org_created(sender, instance, created, **kwargs):
    if not created:
        return
    owner = instance.owner
    if not owner:
        return
    fire_outreach_webhook.delay('trial_started', {
        'user_id': owner.id,
        'email': owner.email,
        'first_name': owner.first_name,
        'last_name': owner.last_name,
        'company_name': instance.name,
        'phone': getattr(owner, 'phone', ''),
        'country': getattr(instance, 'country', ''),
        'source': 'signup',
        'trial_expires_at': (
            instance.trial_end_date.isoformat()
            if hasattr(instance, 'trial_end_date') and instance.trial_end_date
            else ''
        ),
    })

# 2. Supplier connected - when a VendorConnection is created
@receiver(post_save, sender=VendorConnection)  # adjust model name
def on_supplier_connected(sender, instance, created, **kwargs):
    if not created:
        return
    org = instance.organization
    owner = org.owner
    fire_outreach_webhook.delay('supplier_connected', {
        'user_id': owner.id,
        'email': owner.email,
        'supplier_name': instance.vendor.name,
        'suppliers_connected': org.vendor_connections.count(),
    })

# 3. First quote created
@receiver(post_save, sender=Quote)
def on_quote_created(sender, instance, created, **kwargs):
    if not created:
        return
    org = instance.organization
    owner = org.owner
    # Only fire on first quote
    if Quote.objects.filter(organization=org).count() == 1:
        fire_outreach_webhook.delay('first_quote_created', {
            'user_id': owner.id,
            'email': owner.email,
            'quote_total': float(instance.total or 0),
            'currency': instance.currency or 'EUR',
        })

# 4. Subscription started - when Stripe webhook confirms payment
# This hooks into the existing Stripe webhook processing in core/webhook_views.py
# After successful subscription creation, add:
fire_outreach_webhook.delay('subscription_started', {
    'user_id': owner.id,
    'email': owner.email,
    'plan': subscription.plan_name,
    'mrr': float(subscription.amount),
    'currency': subscription.currency,
})

# 5 & 6. Trial expiring / expired - Celery Beat scheduled tasks
# Add to existing celery beat schedule:

@shared_task
def check_expiring_trials():
    """Run daily. Fire webhook for trials expiring in 3 days."""
    from django.utils.timezone import now
    from datetime import timedelta

    expiry_date = (now() + timedelta(days=3)).date()
    # Find orgs with trial ending in 3 days that haven't subscribed
    for org in Organization.objects.filter(
        trial_end_date__date=expiry_date,
        subscription__isnull=True,  # no active subscription
    ):
        owner = org.owner
        fire_outreach_webhook.delay('trial_expiring', {
            'user_id': owner.id,
            'email': owner.email,
            'trial_expires_at': org.trial_end_date.isoformat(),
            'has_connected_supplier': org.vendor_connections.exists(),
            'has_created_quote': Quote.objects.filter(organization=org).exists(),
        })

@shared_task
def check_expired_trials():
    """Run daily. Fire webhook for trials that expired yesterday."""
    from django.utils.timezone import now
    from datetime import timedelta

    expired_date = (now() - timedelta(days=1)).date()
    for org in Organization.objects.filter(
        trial_end_date__date=expired_date,
        subscription__isnull=True,
    ):
        owner = org.owner
        fire_outreach_webhook.delay('trial_expired', {
            'user_id': owner.id,
            'email': owner.email,
            'had_connected_supplier': org.vendor_connections.exists(),
            'had_created_quote': Quote.objects.filter(organization=org).exists(),
        })
```

#### TaggIQ environment variables

```bash
# Add to TaggIQ .env
OUTREACH_WEBHOOK_URL=https://outreach.taggiq.com/api/webhooks/taggiq/
OUTREACH_WEBHOOK_SECRET=<generate-64-char-random-string>
```

```python
# Add to TaggIQ settings.py
OUTREACH_WEBHOOK_URL = os.environ.get('OUTREACH_WEBHOOK_URL', '')
OUTREACH_WEBHOOK_SECRET = os.environ.get('OUTREACH_WEBHOOK_SECRET', '')
```

#### TaggIQ Celery Beat additions

```python
# Add to TaggIQ celery beat schedule
CELERY_BEAT_SCHEDULE = {
    # ... existing tasks ...
    'check-expiring-trials': {
        'task': 'core.tasks.check_expiring_trials',
        'schedule': crontab(hour=8, minute=0),  # 8am daily
    },
    'check-expired-trials': {
        'task': 'core.tasks.check_expired_trials',
        'schedule': crontab(hour=9, minute=0),  # 9am daily
    },
}
```

### Phase 6C: Lifecycle Campaigns in Paperclip

Create 4 new campaigns with email templates. These are triggered by webhook events, not by the daily cron scrape-and-send cycle. They use the same `send_sequences` infrastructure - the webhook creates the prospect, and the next cron run picks them up.

#### Campaign 1: TaggIQ Trial Activation

**Trigger:** `trial_started` webhook
**Goal:** Get the user to connect their first supplier
**From:** `prakash@taggiq.com`

| Seq | Day | Subject A | Subject B | Theme |
|---|---|---|---|---|
| 1 | 0 | Welcome to TaggIQ - one thing to do first | {{FNAME}}, your trial is live | Connect a supplier in 60 seconds |
| 2 | 2 | 500 suppliers, one search | {{FNAME}}, quick setup tip | Show SourceIQ value - search suppliers |
| 3 | 5 | How to quote 10x faster | {{FNAME}}, most people miss this step | Connect search to quoting workflow |
| 4 | 8 | Need a hand getting started? | {{FNAME}}, quick question | Personal offer to help - calendar link |

#### Campaign 2: TaggIQ Trial Conversion

**Trigger:** `first_quote_created` webhook (prospect is activated)
**Goal:** Convert to paid subscription
**From:** `prakash@taggiq.com`

| Seq | Day | Subject A | Subject B | Theme |
|---|---|---|---|---|
| 1 | 0 | Nice - your first quote is live | {{FNAME}}, you're ahead of most shops | Congratulate + show next features (orders, invoicing) |
| 2 | 5 | From quote to invoice in one click | {{FNAME}}, the part most people love | Show full workflow value |
| 3 | 12 | Your trial wrap-up | {{FNAME}}, quick thought before your trial ends | Soft conversion ask - pricing, no pressure |

#### Campaign 3: TaggIQ Trial Expiry

**Trigger:** `trial_expiring` webhook (3 days before expiry)
**Goal:** Urgency - subscribe before losing access
**From:** `prakash@taggiq.com`

| Seq | Day | Subject A | Subject B | Theme |
|---|---|---|---|---|
| 1 | 0 | Your TaggIQ trial ends in 3 days | {{FNAME}}, heads up on your trial | What they'll lose - data stays safe though |
| 2 | 2 | Last day - your data is safe | {{FNAME}}, one more day | Final nudge - data preserved, reactivate anytime |

#### Campaign 4: TaggIQ Win-Back

**Trigger:** `trial_expired` webhook
**Goal:** Re-engage churned trials
**From:** `prakash@taggiq.com`

| Seq | Day | Subject A | Subject B | Theme |
|---|---|---|---|---|
| 1 | 3 | Your TaggIQ data is still there | {{FNAME}}, we kept everything | Data preserved, one click to resume |
| 2 | 10 | What held you back? | {{FNAME}}, honest question | Ask for feedback - understand churn reason |
| 3 | 21 | New in TaggIQ this month | {{FNAME}}, thought you'd want to see this | Product updates since they left |

### Phase 6D: Security Hardening

| # | Task | Size | Notes |
|---|---|---|---|
| 6D.1 | Add `TAGGIQ_WEBHOOK_SECRET` to Paperclip .env | S | Same value as TaggIQ's `OUTREACH_WEBHOOK_SECRET` |
| 6D.2 | Add `TAGGIQ_WEBHOOK_SECRET` to Paperclip settings.py | S | `settings.TAGGIQ_WEBHOOK_SECRET` |
| 6D.3 | Restrict `ALLOWED_HOSTS` in Paperclip settings | S | `['outreach.taggiq.com', 'localhost']` - no more wildcard |
| 6D.4 | Add API key auth to existing Paperclip endpoints | M | Simple `X-API-Key` header check for non-webhook endpoints |
| 6D.5 | Add rate limiting to webhook endpoint | S | Max 100 requests/minute (generous, but prevents abuse) |

---

## Nginx Configuration

Install on EC2 host (outside Docker). Reverse proxy HTTPS to Docker port 8002.

```nginx
# /etc/nginx/conf.d/outreach.conf

server {
    listen 443 ssl;
    server_name outreach.taggiq.com;

    ssl_certificate /etc/letsencrypt/live/outreach.taggiq.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/outreach.taggiq.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # Webhook endpoint - allow larger payloads
    location /api/webhooks/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 1m;
    }

    # All other API endpoints
    location /api/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 1m;
    }

    # Django admin (restrict to Prakash's IP)
    location /admin/ {
        allow <PRAKASH_IP>;
        deny all;
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Block everything else
    location / {
        return 404;
    }
}

server {
    listen 80;
    server_name outreach.taggiq.com;
    return 301 https://$host$request_uri;
}
```

---

## Backup Changes for AWS

The existing `backup_to_gdrive.sh` already supports Docker PostgreSQL (pg_dump via `docker exec`). Two changes needed:

1. **Install rclone on EC2** and configure Google Drive OAuth
2. **Add backup to Docker cron** - update `docker/cron-entrypoint.sh`:

```bash
# Add to cron-entrypoint.sh cron jobs:
# Nightly backup at 23:00
0 23 * * * root /app/backup_to_gdrive.sh >> /tmp/outreach_backup.log 2>&1
```

The backup script's fallback logic (Docker pg_dump -> SQLite if container down) already handles both cases.

---

## Webhook Payload Contract

### Request format (TaggIQ -> Paperclip)

```
POST /api/webhooks/taggiq/
Content-Type: application/json
X-TaggIQ-Signature: sha256=<hmac_sha256_hex>
X-TaggIQ-Event: <event_type>
X-TaggIQ-Delivery: <uuid>

{
    "event": "<event_type>",
    "timestamp": "2026-04-10T14:30:00Z",
    "data": { ... event-specific fields ... }
}
```

### Response format

```json
// Success
{"status": "ok", "delivery_id": "<uuid>"}

// Already processed (idempotent)
{"status": "already_processed"}

// Auth failure
{"error": "Invalid signature"}  // 401

// Bad request
{"error": "Invalid JSON"}       // 400
{"error": "Missing delivery ID"}  // 400
```

### Event payloads

**trial_started:**
```json
{
    "user_id": 142,
    "email": "john@printhub.com",
    "first_name": "John",
    "last_name": "Smith",
    "company_name": "PrintHub Ltd",
    "phone": "+1-555-0123",
    "country": "US",
    "source": "signup",
    "trial_expires_at": "2026-05-10T14:30:00Z"
}
```

**supplier_connected:**
```json
{
    "user_id": 142,
    "email": "john@printhub.com",
    "supplier_name": "SanMar",
    "suppliers_connected": 1
}
```

**first_quote_created:**
```json
{
    "user_id": 142,
    "email": "john@printhub.com",
    "quote_total": 450.00,
    "currency": "USD",
    "items_count": 3
}
```

**trial_expiring:**
```json
{
    "user_id": 142,
    "email": "john@printhub.com",
    "trial_expires_at": "2026-05-10T14:30:00Z",
    "has_connected_supplier": true,
    "has_created_quote": true,
    "has_created_order": false
}
```

**subscription_started:**
```json
{
    "user_id": 142,
    "email": "john@printhub.com",
    "plan": "growth",
    "mrr": 149.00,
    "currency": "EUR"
}
```

**trial_expired:**
```json
{
    "user_id": 142,
    "email": "john@printhub.com",
    "had_connected_supplier": true,
    "had_created_quote": true,
    "had_created_order": false
}
```

---

## Full Task Board

### Sprint 5: AWS Deployment

| # | Task | Phase | Size | Dependencies | Status |
|---|---|---|---|---|---|
| 5A.1 | Launch EC2 t3.micro (eu-west-1, same VPC) | 5A | S | Sprint 4 done | Pending |
| 5A.2 | Create security group `outreach-sg` | 5A | S | None | Pending |
| 5A.3 | Allocate Elastic IP | 5A | S | 5A.1 | Pending |
| 5A.4 | Install Docker + docker-compose on EC2 | 5A | S | 5A.1 | Pending |
| 5A.5 | DNS: `outreach.taggiq.com` A record | 5A | S | 5A.3 | Pending |
| 5A.6 | Install Nginx + certbot, configure SSL | 5A | S | 5A.5 | Pending |
| 5B.1 | Clone repo on EC2 | 5B | S | 5A.4 | Pending |
| 5B.2 | Copy `.env` to EC2 | 5B | S | 5B.1 | Pending |
| 5B.3 | Start PostgreSQL, verify healthy | 5B | S | 5B.1 | Pending |
| 5B.4 | Verify Django starts with empty DB | 5B | S | 5B.3 | Pending |
| 5C.1 | **STOP local cron** | 5C | S | 5B.4 | Pending |
| 5C.2 | Wait for running jobs to finish | 5C | S | 5C.1 | Pending |
| 5C.3 | Dump local PostgreSQL | 5C | S | 5C.2 | Pending |
| 5C.4 | Transfer dump to AWS via scp | 5C | S | 5C.3 | Pending |
| 5C.5 | Restore dump on AWS PostgreSQL | 5C | S | 5C.4 | Pending |
| 5C.6 | Verify row counts match local | 5C | M | 5C.5 | Pending |
| 5C.7 | `docker compose up -d` all services | 5C | S | 5C.6 | Pending |
| 5C.8 | Verify send_sequences --dry-run | 5C | S | 5C.7 | Pending |
| 5C.9 | Verify handle_replies --dry-run | 5C | S | 5C.7 | Pending |
| 5C.10 | Test Nginx + SSL externally | 5C | S | 5C.7, 5A.6 | Pending |
| 5C.11 | Update Vapi webhook URL | 5C | S | 5C.10 | Pending |
| 5D.1 | Monitor first automated send | 5D | M | 5C.11 | Pending |
| 5D.2 | Monitor first reply handling | 5D | M | 5C.11 | Pending |
| 5D.3 | Verify nightly backup | 5D | S | 5C.11 | Pending |
| 5D.4 | Compare daily send volumes for 3 days | 5D | S | 5D.1 | Pending |
| 5D.5 | Keep local as cold standby 7 days | 5D | S | 5D.4 | Pending |

### Sprint 6: TaggIQ Integration

| # | Task | Phase | Size | Dependencies | Status |
|---|---|---|---|---|---|
| 6A.1 | WebhookEvent model + migration (Paperclip) | 6A | S | Sprint 5 | Pending |
| 6A.2 | Add Prospect fields: taggiq_user_id, trial dates | 6A | S | None | Pending |
| 6A.3 | POST /api/webhooks/taggiq/ endpoint (Paperclip) | 6A | M | 6A.1, 6A.2 | Pending |
| 6A.4 | Event handler logic: 6 event types | 6A | M | 6A.3 | Pending |
| 6A.5 | URL routing for webhook endpoint | 6A | S | 6A.3 | Pending |
| 6B.1 | fire_outreach_webhook Celery task (TaggIQ) | 6B | S | None | Pending |
| 6B.2 | Django signals: trial_started, supplier_connected | 6B | M | 6B.1 | Pending |
| 6B.3 | Django signals: first_quote, subscription | 6B | M | 6B.1 | Pending |
| 6B.4 | Celery Beat tasks: trial_expiring, trial_expired | 6B | S | 6B.1 | Pending |
| 6B.5 | Add env vars to TaggIQ .env + settings.py | 6B | S | 6A.5 | Pending |
| 6C.1 | Create Trial Activation campaign + 8 templates | 6C | M | 6A.4 | Pending |
| 6C.2 | Create Trial Conversion campaign + 6 templates | 6C | S | 6A.4 | Pending |
| 6C.3 | Create Trial Expiry campaign + 4 templates | 6C | S | 6A.4 | Pending |
| 6C.4 | Create Win-Back campaign + 6 templates | 6C | S | 6A.4 | Pending |
| 6D.1 | Add TAGGIQ_WEBHOOK_SECRET to Paperclip .env | 6D | S | 6A.3 | Pending |
| 6D.2 | Restrict ALLOWED_HOSTS | 6D | S | Sprint 5 | Pending |
| 6D.3 | Rate limiting on webhook endpoint | 6D | S | 6A.3 | Pending |
| 6E.1 | End-to-end test: manual webhook fire -> verify prospect created | 6E | M | All above | Pending |
| 6E.2 | End-to-end test: TaggIQ staging signup -> verify full flow | 6E | M | 6E.1 | Pending |

---

## Timeline

| Sprint | What | When | Duration |
|---|---|---|---|
| Sprint 4 | Docker + PostgreSQL locally | 2026-04-16 (after monitoring period) | 1 session |
| Local Docker monitoring | Verify Docker cron for 2+ business days | 2026-04-17 to 2026-04-18 | 2 days |
| Sprint 5 | AWS deployment + migration | 2026-04-21 (Monday) | 1 session + verification |
| AWS monitoring | Verify AWS cron for 2+ business days | 2026-04-22 to 2026-04-23 | 2 days |
| Sprint 6 | TaggIQ webhook bridge | 2026-04-24 | 1-2 sessions |
| Integration testing | End-to-end webhook verification | 2026-04-25 | 1 day |

**Total elapsed time:** ~2 weeks from Sprint 4 start to fully operational webhook bridge.

---

## What Changes for Day-to-Day Operations

| Before (local Mac) | After (AWS) |
|---|---|
| Mac must be open and awake for cron | Runs 24/7 on EC2, Mac irrelevant |
| Vapi webhooks can't reach localhost | Vapi webhooks hit `outreach.taggiq.com` |
| Check logs: `cat /tmp/campaigns_daily.log` | Check logs: `ssh outreach && docker logs outreach_cron` |
| Django admin: `localhost:8002/admin/` | Django admin: `https://outreach.taggiq.com/admin/` |
| API: `localhost:8002/api/dashboard/` | API: `https://outreach.taggiq.com/api/dashboard/` |
| Claude skills run locally via `venv/bin/python` | Claude skills need SSH or remote API call |
| Reply monitor uses macOS notifications | No desktop notifications (check logs or build Slack alert) |

### Claude skill adaptation

After AWS migration, the email expert skills (`/taggiq-email-expert`, `/fp-email-expert`) that currently run `venv/bin/python manage.py check_replies` locally will need updating. Two options:

1. **SSH execution:** Skills SSH into EC2 and run commands remotely
2. **Keep a local read-only copy:** Local Django points to AWS PostgreSQL (read-only) for the skills that need DB access

Recommendation: Option 1 (SSH) is simpler and avoids split-brain. Add an SSH alias:

```bash
# ~/.ssh/config
Host outreach
    HostName <ELASTIC_IP>
    User ec2-user
    IdentityFile ~/.ssh/outreach-key.pem
```

Then skills run: `ssh outreach 'cd paperclip-outreach && docker exec outreach_web python manage.py check_replies'`
