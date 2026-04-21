# Sprint 9 - Observability & Analytics Dashboard

**Author:** CTO Architect
**Date:** 2026-04-21
**Reviewed by:** Sales Director (KPI priorities)
**Implements:** Pipeline analytics, daily KPI email, health alerting

---

## Problem Statement

Paperclip Outreach runs a fully autonomous sales pipeline (email sequences, AI replies, calls, nudges) but has no way to see how it's performing without running Django shell commands. A "24/7 zero headcount" system that fails silently is worse than a manual one. Prakash needs:

1. A single page that answers "how's the pipeline?" in 10 seconds
2. A morning email that tells him what to act on today
3. Alerting when the system breaks (auth expiry, stuck replies, send failures)

## Design Principles

1. **API-first** - Build analytics endpoints that the dashboard consumes. These endpoints are reusable when Paperclip is productized.
2. **Zero new models** - All data already exists in EmailLog, CallLog, InboundEmail, ProspectEvent, AIUsageLog, Prospect. This is a read/aggregation problem.
3. **Django templates, not SPA** - No npm, no build step, no frontend framework. One HTML template + Chart.js CDN + Tailwind CDN.
4. **Action-oriented** - Show names not just numbers. "Sharon Bates waiting 3hrs" not "1 pending reply."
5. **No new dependencies** - Pure Django. No Grafana, no Metabase, no Redis.

---

## KPI Hierarchy (Sales Director approved)

### Tier 1 - Daily Email (check every morning)

| KPI | Source | Query |
|-----|--------|-------|
| Emails sent yesterday | `EmailLog.filter(status='sent', created_at__date=yesterday)` | Count by campaign |
| Replies received | `InboundEmail.filter(received_at__date=yesterday)` | Count, list names |
| New interested (with names) | `ProspectEvent.filter(to_status='interested', created_at__date=yesterday)` | Name, company, campaign |
| Demos booked (with names) | `ProspectEvent.filter(to_status='demo_scheduled', created_at__date=yesterday)` | Name, company |
| Avg response time | `InboundEmail.filter(auto_replied=True)` -> `reply_sent_at - received_at` | Minutes avg |
| Pending replies >2hrs | `InboundEmail.filter(needs_reply=True, replied=False, received_at__lt=2hrs_ago)` | Name, company, hours waiting |
| Hot leads cooling off | `Prospect.filter(status='interested', last_emailed_at__lt=7d_ago)` | Name, days since last touch |

### Tier 2 - Weekly Dashboard

| KPI | Source |
|-----|--------|
| Reply rate by campaign | EmailLog(sent) vs InboundEmail per campaign |
| Reply rate by sequence # | EmailLog.sequence_number vs InboundEmail per seq |
| Funnel conversion rates | ProspectEvent aggregated transitions |
| Hot lead aging histogram | Prospect(interested) days since status change |
| AI cost per demo | AIUsageLog.sum(cost_usd) / ProspectEvent(to_status=demo_scheduled) |
| Win/loss from interested | ProspectEvent from interested -> demo vs interested -> not_interested |

### Tier 3 - Monthly Dashboard

| KPI | Source |
|-----|--------|
| Campaign ranking by conversion | Interested count / emails sent per campaign |
| A/B variant performance | EmailLog.ab_variant vs InboundEmail reply rates |
| Channel attribution | ProspectEvent.triggered_by breakdown |
| Segment/tier performance | Prospect.segment/tier vs conversion |

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│  /dashboard/  (Django template + Chart.js CDN)   │
│  ┌────────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Pipeline   │ │ Funnel   │ │ Health &      │  │
│  │ Numbers    │ │ Chart    │ │ Alerts        │  │
│  │ + Names    │ │ + Trends │ │ + Actions     │  │
│  └────────────┘ └──────────┘ └───────────────┘  │
└───────────────────┬──────────────────────────────┘
                    │ AJAX calls
┌───────────────────▼──────────────────────────────┐
│  campaigns/services/analytics.py (NEW)           │
│                                                   │
│  get_pipeline_kpis(product, days)                │
│  get_funnel_transitions(product, days)           │
│  get_daily_trends(product, days)                 │
│  get_campaign_rankings(product, days)            │
│  get_health_status()                             │
│  get_action_items()                              │
│  build_daily_email_context()                     │
└───────────────────┬──────────────────────────────┘
                    │ queries
┌───────────────────▼──────────────────────────────┐
│  Existing Models (zero changes)                   │
│  EmailLog | CallLog | InboundEmail | Prospect    │
│  ProspectEvent | AIUsageLog | MailboxConfig      │
└──────────────────────────────────────────────────┘
```

### Module Boundary: `campaigns/services/analytics.py`

All analytics logic lives in ONE new service file. No scattered queries in views or commands.

**Rules:**
- Pure read-only queries. Never mutates data.
- Every function takes `product_slug=None` and `days=7` as optional filters.
- Returns plain dicts (JSON-serializable). No custom classes needed.
- Uses `ProspectEvent` for flow metrics (not point-in-time Prospect counts, except for current funnel snapshot).
- Handles empty data gracefully (0, not None; empty lists, not errors).

---

## API Endpoints

All new endpoints go under `/api/analytics/` prefix. No auth (same as existing API - local/EC2 only).

### `GET /api/analytics/pipeline/`

**Params:** `?product=taggiq&days=7`

**Response:**
```json
{
  "period": {"from": "2026-04-14", "to": "2026-04-21", "days": 7},
  "email": {
    "sent": 145,
    "sent_today": 12,
    "replies_received": 7,
    "reply_rate_pct": 4.8,
    "auto_replied": 5,
    "pending_reply": 2,
    "avg_response_minutes": 8.2
  },
  "calls": {
    "placed": 0,
    "answered": 0,
    "answer_rate_pct": 0.0,
    "demos_from_calls": 0
  },
  "funnel": {
    "new": 1842, "contacted": 1650, "interested": 48,
    "engaged": 12, "demo_scheduled": 5, "design_partner": 3,
    "customer": 1, "follow_up_later": 22,
    "not_interested": 180, "opted_out": 95
  },
  "velocity": {
    "new_to_contacted": 42,
    "contacted_to_interested": 8,
    "interested_to_demo": 2
  },
  "ai": {
    "cost_mtd_usd": 12.45,
    "cost_period_usd": 3.20,
    "replies_generated": 34,
    "cost_per_demo": 2.49
  },
  "health": {
    "stuck_interested_gt7d": 4,
    "pending_replies_gt2h": 2,
    "last_send_at": "2026-04-21T11:42:00Z",
    "last_reply_check_at": "2026-04-21T11:50:00Z",
    "cron_healthy": true
  }
}
```

### `GET /api/analytics/funnel/`

**Params:** `?product=taggiq&days=30`

**Response:**
```json
{
  "transitions": [
    {"from_status": "new", "to_status": "contacted", "count": 182, "avg_days": 1.2},
    {"from_status": "contacted", "to_status": "interested", "count": 14, "avg_days": 12.5},
    {"from_status": "interested", "to_status": "demo_scheduled", "count": 3, "avg_days": 3.8},
    {"from_status": "interested", "to_status": "not_interested", "count": 6, "avg_days": 18.2},
    {"from_status": "interested", "to_status": "follow_up_later", "count": 8, "avg_days": 14.0}
  ],
  "win_loss": {
    "from_interested_to_demo": 3,
    "from_interested_to_lost": 6,
    "win_rate_pct": 33.3
  }
}
```

### `GET /api/analytics/trends/`

**Params:** `?product=taggiq&days=14`

**Response:**
```json
{
  "series": [
    {"date": "2026-04-08", "emails_sent": 15, "replies": 1, "interested": 0, "demos": 0, "ai_cost_usd": 0.82},
    {"date": "2026-04-09", "emails_sent": 14, "replies": 2, "interested": 1, "demos": 0, "ai_cost_usd": 1.10}
  ]
}
```

### `GET /api/analytics/campaigns/`

**Params:** `?product=taggiq&days=30`

**Response:**
```json
{
  "campaigns": [
    {
      "id": "uuid", "name": "TaggIQ BNI Ireland",
      "prospects": 67, "emails_sent": 312, "replies": 18,
      "reply_rate_pct": 5.8, "interested": 4, "demos": 1,
      "conversion_rate_pct": 1.4,
      "sequence_stats": [
        {"seq": 1, "sent": 67, "replies": 3, "reply_rate_pct": 4.5},
        {"seq": 2, "sent": 58, "replies": 5, "reply_rate_pct": 8.6},
        {"seq": 3, "sent": 45, "replies": 6, "reply_rate_pct": 13.3}
      ]
    }
  ],
  "ranked_by": "reply_rate_pct"
}
```

### `GET /api/analytics/actions/`

**Params:** `?product=taggiq`

The "DO NOW" list. Returns actionable items with prospect names.

**Response:**
```json
{
  "pending_replies": [
    {"prospect_name": "Sharon Bates", "company": "Keynote Marketing", "hours_waiting": 3.2, "subject": "Re: artwork approvals", "inbound_id": "uuid"}
  ],
  "cooling_leads": [
    {"prospect_name": "Paul Rivers", "company": "Print RFT", "status": "interested", "days_since_touch": 9, "campaign": "TaggIQ BNI Promo Global"}
  ],
  "upcoming_demos": [
    {"prospect_name": "Linda Prudden", "company": "Linton Merch", "status": "demo_scheduled", "campaign": "TaggIQ BNI Promo Global"}
  ],
  "recent_wins": [
    {"prospect_name": "Jon Lambert", "company": "Print Solutions", "to_status": "interested", "when": "2026-04-21T09:30:00Z", "triggered_by": "ai_reply"}
  ],
  "system_alerts": [
    {"level": "warn", "message": "CLI auth token expires in 2 days", "action": "Run: docker exec -it outreach_cron claude setup-token"}
  ]
}
```

### `GET /api/health/`

System health check (for monitoring/cron).

**Response:**
```json
{
  "status": "healthy",
  "checks": {
    "last_send": {"status": "ok", "value": "2026-04-21T11:42:00Z", "message": "12 emails sent today"},
    "last_reply_check": {"status": "ok", "value": "2026-04-21T11:50:00Z", "message": "10 min ago"},
    "pending_replies": {"status": "ok", "value": 0, "message": "No pending replies"},
    "auth_token": {"status": "warn", "value": "2026-04-23T00:00:00Z", "message": "Expires in 2 days"},
    "db_connection": {"status": "ok", "value": null, "message": "Connected"}
  },
  "alerts": []
}
```

---

## Task Board

| # | Task | Phase | Size | Dependencies | Acceptance Criteria |
|---|------|-------|------|--------------|---------------------|
| 1 | Create `campaigns/services/analytics.py` | 1 | L | None | All 7 functions implemented, tested with Django shell |
| 2 | Add `/api/analytics/pipeline/` endpoint | 1 | S | Task 1 | Returns correct JSON, filterable by product/days |
| 3 | Add `/api/analytics/funnel/` endpoint | 1 | S | Task 1 | ProspectEvent transitions with avg_days + win/loss |
| 4 | Add `/api/analytics/trends/` endpoint | 1 | S | Task 1 | Daily time series, correct date grouping |
| 5 | Add `/api/analytics/campaigns/` endpoint | 1 | S | Task 1 | Campaign ranking + per-sequence reply rates |
| 6 | Add `/api/analytics/actions/` endpoint | 1 | M | Task 1 | Returns named action items (pending, cooling, demos, wins, alerts) |
| 7 | Add `/api/health/` endpoint | 1 | S | None | System health checks as JSON |
| 8 | Wire URL routes for all endpoints | 1 | XS | Tasks 2-7 | All endpoints reachable |
| 9 | Create `daily_kpi_email` management command | 2 | M | Task 1 | Sends HTML email to Prakash via SES with Tier 1 KPIs + action items |
| 10 | Add `daily_kpi_email` to cron (8am weekdays) | 2 | XS | Task 9 | Runs on EC2 cron container |
| 11 | Add `brain_doctor` to cron (8am daily) | 2 | XS | None | Catches auth expiry, logs to /tmp/outreach_health.log |
| 12 | Create dashboard Django template | 3 | L | Tasks 2-7 | Single page at /dashboard/ with pipeline numbers, funnel chart, trends, action items |
| 13 | Dashboard URL route + view | 3 | S | Task 12 | Renders template, no login required |
| 14 | Anomaly detection in daily email | 3 | S | Task 9 | Flags: 0 sends on weekday, reply rate drop >50%, auth expiry <48h, stuck replies >6h |
| 15 | Deploy to EC2 | 3 | S | All | All endpoints live, cron jobs active, dashboard accessible |

---

## Phase Breakdown

### Phase 1 - Analytics Service + API Endpoints (Tasks 1-8)

The foundation. All analytics logic in `campaigns/services/analytics.py`, exposed via 6 API endpoints.

**Key implementation notes for `analytics.py`:**

```python
# campaigns/services/analytics.py
"""
Read-only analytics service for pipeline KPIs.
All functions return plain dicts (JSON-serializable).
Never mutates data.
"""
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Sum, F, Q, ExpressionWrapper, DurationField
from django.db.models.functions import TruncDate

from campaigns.models import (
    EmailLog, CallLog, InboundEmail, Prospect,
    ProspectEvent, AIUsageLog, Campaign
)


def get_pipeline_kpis(product_slug=None, days=7):
    """Master KPI endpoint - all numbers in one call."""
    ...

def get_funnel_transitions(product_slug=None, days=30):
    """ProspectEvent transitions aggregated with avg timing."""
    ...

def get_daily_trends(product_slug=None, days=14):
    """Daily rollups for time series charts."""
    ...

def get_campaign_rankings(product_slug=None, days=30):
    """Campaigns ranked by reply rate, with per-sequence breakdown."""
    ...

def get_action_items(product_slug=None):
    """Named action items: pending replies, cooling leads, upcoming demos."""
    ...

def get_health_status():
    """System health checks."""
    ...

def build_daily_email_context(product_slug=None):
    """Assembles all data needed for the daily KPI email."""
    ...
```

**View structure (in `campaigns/views.py`):**

Each endpoint is a simple function view that calls the analytics service and returns JsonResponse. Pattern:

```python
@require_GET
def analytics_pipeline(request):
    product = request.GET.get('product')
    days = int(request.GET.get('days', 7))
    data = analytics.get_pipeline_kpis(product_slug=product, days=days)
    return JsonResponse(data)
```

**URL routes (in `campaigns/urls.py`):**

```python
path('api/analytics/pipeline/', views.analytics_pipeline),
path('api/analytics/funnel/', views.analytics_funnel),
path('api/analytics/trends/', views.analytics_trends),
path('api/analytics/campaigns/', views.analytics_campaigns),
path('api/analytics/actions/', views.analytics_actions),
path('api/health/', views.health_check),
```

### Phase 2 - Daily KPI Email + Health Alerting (Tasks 9-11)

**Daily email command** (`campaigns/management/commands/daily_kpi_email.py`):

- Calls `analytics.build_daily_email_context()` to get all data
- Renders HTML email template (`campaigns/templates/emails/daily_kpi.html`)
- Sends via SES to `prakash@taggiq.com` (or configurable)
- Includes anomaly detection (Task 14 adds to this)

**Email format (action-oriented, per Sales Director):**

```
Subject: Pipeline Daily - 21 Apr: 12 sent, 2 replies, 1 demo

DO NOW:
  -> Reply pending 3hrs: Sharon Bates (Keynote Marketing)
  -> Demo tomorrow: Linda Prudden (Linton Merch)

WINS:
  1 new interested: Jon Lambert, Print Solutions Dublin
  AI replied to 3 inbounds (avg 8 min response time)

WATCH:
  Paul Rivers (Print RFT) - 9 days in interested, no demo booked
  Declan Power (Promotex) - 12 days since last touch

NUMBERS:
  Sent: 12 | Replies: 2 (4.8%) | Demos: 0 | AI cost: $0.82
  MTD: 145 sent | 7 replies | 2 demos | $12.45 AI cost

SYSTEM:
  OK All cron jobs ran on schedule
  OK Auth token valid (4 days remaining)
```

**Cron additions to `docker/cron-entrypoint.sh`:**

```bash
# Daily KPI email at 8am Mon-Fri
0 8 * * 1-5 root . /app/docker/.env.cron && cd /app && python manage.py daily_kpi_email >> /tmp/outreach_kpi.log 2>&1

# Health check at 8am daily (including weekends)
0 8 * * * root . /app/docker/.env.cron && cd /app && python manage.py brain_doctor >> /tmp/outreach_health.log 2>&1
```

### Phase 3 - Dashboard UI + Anomalies (Tasks 12-15)

**Dashboard template** (`campaigns/templates/dashboard.html`):

Single HTML file, no build step. Uses:
- Chart.js CDN for funnel chart + trend lines
- Tailwind CDN for styling
- Vanilla JS `fetch()` calls to analytics API endpoints
- Auto-refreshes every 5 minutes

**Layout:**

```
┌─────────────────────────────────────────────────┐
│  PAPERCLIP OUTREACH - Pipeline Dashboard        │
│  [TaggIQ] [Fully Promoted] [All]   [7d|30d|90d]│
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│  │ Sent │ │Reply │ │Inter-│ │Demos │ │  AI  │  │
│  │ 145  │ │ 4.8% │ │ested │ │  5   │ │$12.45│  │
│  │      │ │      │ │  48  │ │      │ │      │  │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │
│                                                  │
│  ┌─────────────────────┐ ┌─────────────────────┐│
│  │   FUNNEL CHART      │ │   TRENDS (14d)      ││
│  │   new: 1842         │ │   ~~~~~~            ││
│  │   contacted: 1650   │ │   emails --         ││
│  │   interested: 48    │ │   replies --         ││
│  │   demo: 5           │ │   interested --     ││
│  │   customer: 1       │ │                     ││
│  └─────────────────────┘ └─────────────────────┘│
│                                                  │
│  ┌─────────────────────────────────────────────┐│
│  │  ACTION ITEMS                                ││
│  │  DO NOW:                                     ││
│  │    ! Sharon Bates - reply pending 3hrs       ││
│  │    ! Linda Prudden - demo tomorrow           ││
│  │  COOLING:                                    ││
│  │    Paul Rivers - 9d in interested            ││
│  │    Declan Power - 12d since last touch       ││
│  └─────────────────────────────────────────────┘│
│                                                  │
│  ┌─────────────────────────────────────────────┐│
│  │  CAMPAIGN RANKINGS (by reply rate)           ││
│  │  1. TaggIQ BNI Ireland    5.8%  67 prospects ││
│  │  2. TaggIQ BNI Promo      3.2% 782 prospects ││
│  │  3. TaggIQ Ireland P&P    1.1% 586 prospects ││
│  └─────────────────────────────────────────────┘│
│                                                  │
│  ┌─────────────────────────────────────────────┐│
│  │  SYSTEM HEALTH                    All OK     ││
│  │  Last send: 11:42 | Last reply check: 11:50 ││
│  │  Auth: valid (4d) | Pending: 0               ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**Dashboard view:**

```python
def dashboard_view(request):
    """Renders the analytics dashboard. No API call - serves the template
    which then fetches data via JS from the analytics endpoints."""
    return render(request, 'dashboard.html')
```

---

## Implementation Contract

### File locations

| File | Purpose |
|------|---------|
| `campaigns/services/analytics.py` | NEW - all analytics query logic |
| `campaigns/views.py` | ADD 6 view functions (analytics_pipeline, etc) |
| `campaigns/urls.py` | ADD 7 URL routes |
| `campaigns/management/commands/daily_kpi_email.py` | NEW - morning email command |
| `campaigns/templates/dashboard.html` | NEW - single-page dashboard |
| `campaigns/templates/emails/daily_kpi.html` | NEW - email template |
| `docker/cron-entrypoint.sh` | ADD 2 cron lines |

### Anti-patterns (DO NOT)

- Do NOT create new models. All data exists.
- Do NOT add Django REST Framework. Plain JsonResponse is fine.
- Do NOT add npm/webpack/vite. CDN for Chart.js and Tailwind.
- Do NOT add authentication to the dashboard. EC2 is SSH-locked.
- Do NOT duplicate query logic across views. Everything goes through analytics.py.
- Do NOT use raw SQL. Django ORM only (aggregations, annotations, TruncDate).
- Do NOT add a separate settings file. Use existing SES config for the daily email.

### Working state rules

- After Phase 1: `curl localhost:8002/api/analytics/pipeline/` returns valid JSON
- After Phase 2: `python manage.py daily_kpi_email --dry-run` prints email content
- After Phase 3: `/dashboard/` renders with live data
- At every phase: `python manage.py check` passes, existing endpoints unaffected

---

## Rollback

- Phase 1: Delete analytics.py + remove URL routes. Zero migration, zero data impact.
- Phase 2: Remove cron lines. Delete command file. Zero data impact.
- Phase 3: Delete template + remove URL route. Zero data impact.

No migrations, no model changes, no data risk at any phase.

---

## Verification Commands

```bash
# Phase 1
curl -s localhost:8002/api/analytics/pipeline/ | python -m json.tool
curl -s localhost:8002/api/analytics/funnel/?days=30 | python -m json.tool
curl -s localhost:8002/api/analytics/trends/?days=14 | python -m json.tool
curl -s localhost:8002/api/analytics/campaigns/ | python -m json.tool
curl -s localhost:8002/api/analytics/actions/ | python -m json.tool
curl -s localhost:8002/api/health/ | python -m json.tool

# Phase 2
python manage.py daily_kpi_email --dry-run
python manage.py brain_doctor

# Phase 3
# Open http://localhost:8002/dashboard/ in browser
```
