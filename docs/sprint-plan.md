# Paperclip Outreach v2 - Sprint Implementation Plan

**Date:** 2026-04-08
**Last updated:** 2026-04-08
**Reference:** docs/architecture-v2-plan.md
**Approach:** 4 sprints, each ~1 session (2-4 hours). Each sprint is independently shippable.

---

## Current Status

| Sprint | Status | Commit | Date |
|--------|--------|--------|------|
| Sprint 1 | DONE | `6f5bc21` Sprint 1: Multi-tenant models + Organization/Product hierarchy | 2026-04-08 |
| Sprint 2 | DONE | `d3befef` Sprint 2: Service layer + universal sender + 100 email templates seeded | 2026-04-08 |
| Sprint 3 | DONE | `839516a` Sprint 3: Product-scoped suppressions, DB call scripts, universal sender cron | 2026-04-08 |
| Sprint 4 | PENDING | - | Waiting for 5 business days of cron monitoring |
| Sprint 5 | PLANNED | - | AWS deployment (after Sprint 4) |
| Sprint 6 | PLANNED | - | TaggIQ webhook bridge (after Sprint 5) |

**Monitoring period:** 2026-04-09 to 2026-04-15 (Mon-Fri cron sends via send_sequences)
**Sprint 4 earliest start:** 2026-04-16
**Sprint 5-6 plan:** See `docs/aws-deployment-and-taggiq-integration.md`

---

## Sprint 1: Foundation (Multi-Tenant Models + DB Setup) - DONE

**Commit:** `6f5bc21`

### What was built

| Task | Status | Notes |
|------|--------|-------|
| Organization model | DONE | name, slug, owner (nullable), is_active. db_table='organizations' |
| Product model | DONE | FK to Organization, name, slug, is_active. unique_together=(org, slug) |
| Campaign.product_ref FK | DONE | New FK field alongside legacy `product` CharField. Both populated. |
| EmailTemplate model | DONE | FK Campaign, sequence_number, ab_variant, subject/body templates |
| CallScript model | DONE | FK Campaign, segment, first_message |
| PromptTemplate model | DONE | FK Product, feature, system_prompt, model, version |
| AIUsageLog model | DONE | FKs to Org/Product/Campaign/Prospect, token tracking, cost calc |
| Campaign send window fields | DONE | timezone, start/end hour, days, batch_size, inter_send_delay |
| Suppression product FK | DONE | FK to Product (nullable = global). unique_together=(email, product) |
| ScriptInsight learning loop | DONE | baseline/post-change rates, improvement_measured, measured_at |
| Migrations | DONE | 0010_v2_multi_tenant_models + 0011_seed_org_products_link_fks |
| Data migration | DONE | Skillblend Ltd org + 3 products + all 13 campaigns linked |
| Admin registrations | DONE | All new models registered with filters and badges |
| Views.py product filters | DONE | All `campaign__product=` changed to `campaign__product_ref__slug=` |

### Design decision: product_ref not product

The old `product` CharField is kept as `campaign.product` (legacy). The new FK is `campaign.product_ref`. This avoids a dangerous in-place column type change on SQLite. The legacy field will be removed after PostgreSQL migration (Sprint 4).

**How to access:** `campaign.product_ref.slug` for the slug, `campaign.product_ref.organization` for the org. `campaign.product` still works as the legacy string.

---

## Sprint 2: Service Layer + Universal Sender - DONE

**Commit:** `d3befef`

### What was built

| Task | Status | Notes |
|------|--------|-------|
| services/eligibility.py | DONE | get_eligible_prospects(), is_suppressed() with product-scoped FK |
| services/safeguards.py | DONE | daily_remaining(), check_min_gap(), can_send_to_prospect() |
| services/template_resolver.py | DONE | get_template(), render(), determine_variant(). Supports {{FNAME}}, {{COMPANY}}, {{CITY}}, {{YEAR}}, {{SEGMENT}}, {{CHAPTER}}, {{CALENDAR_LINK}} |
| services/send_orchestrator.py | DONE | send_one() - authoritative send path |
| services/ai_tracker.py | DONE | log_ai_call(), get_prompt(), MODEL_PRICING, get_usage_summary() |
| seed_templates command | DONE | 102 EmailTemplate rows seeded (100 from seed_templates + 2 FP BNI manual) |
| send_sequences command | DONE | Universal sender. --product, --campaign, --dry-run, --status, --limit |

### Template coverage

| Campaign | Templates in DB | Notes |
|----------|----------------|-------|
| TaggIQ BNI | 10 (5 seq x 2 variants) | BNI base templates |
| TaggIQ BNI Promo Global | 10 | Same base templates |
| TaggIQ BNI Embroidery Global | 10 | Embroidery overrides (seq 1-4), base seq 5 |
| TaggIQ Ireland Signs | 10 | ireland_signs prefix |
| TaggIQ Ireland Apparel | 10 | ireland_apparel prefix |
| TaggIQ Ireland Print & Promo | 10 | ireland_print prefix |
| TaggIQ London Signs | 10 | london_signs prefix |
| TaggIQ London Apparel | 10 | london_apparel prefix |
| TaggIQ London Print & Promo | 10 | london_print prefix |
| FP Ireland Franchise Recruitment | 10 | FP recruitment sequences |
| FP Dublin BNI Print & Promo | 2 | Seq 1 only (1-2-1 intro). Uses {{CHAPTER}} variable. |
| FP Dublin B2B Corporate Sales | 0 | Campaign not started - needs Emma-voice sequences |
| TaggIQ Launch | 0 | Legacy test campaign, low priority |

### How to use send_sequences

```bash
python manage.py send_sequences                      # All active campaigns
python manage.py send_sequences --product taggiq     # One product
python manage.py send_sequences --campaign "BNI"     # Name substring
python manage.py send_sequences --dry-run            # Preview only
python manage.py send_sequences --status             # Show eligible counts only
python manage.py send_sequences --limit 5            # Max per campaign
```

---

## Sprint 3: Wire Services + Cut Over Cron - DONE

**Commit:** `839516a`

### What was built

| Task | Status | Notes |
|------|--------|-------|
| check_replies.py product-scoped suppressions | DONE | Opt-outs/bounces now created with product FK |
| call_service.py DB call scripts | DONE | Reads from CallScript model, falls back to hardcoded defaults |
| run_campaigns.sh cron cutover | DONE | Now calls `python manage.py send_sequences` instead of 3 scripts |
| views.py refactoring | DEFERRED | API contract must stay stable for backward compat while monitoring |
| process_queue.py refactoring | DEFERRED | Same reason - will refactor after cron proves stable |
| analyze_calls.py AI tracking | DEFERRED | Will wire in when calling goes active |
| CallScript DB seeding | DEFERRED | Will seed when calling campaigns are activated |

### Deferred items rationale

The views.py `/api/send/` endpoint is still called by old sender scripts (as fallback) and by process_queue. Changing its internals to use services during the monitoring period creates unnecessary risk. These will be refactored in a future sprint after the cron cutover is proven stable.

---

## Sprint 4: Docker + PostgreSQL Migration + Cleanup - PENDING

**Earliest start:** 2026-04-16 (after 5 business days of cron monitoring)
**Prerequisite:** No errors in /tmp/campaigns_daily.log for 5 consecutive business days

### Port Allocation (no conflicts)

```
TaggIQ:   postgres=5432, backend=8010, frontend=5180, redis=6379
Kritno:   postgres=5432*, backend=8000, frontend=5173, redis=6379* (*stopped)
Outreach: postgres=5433, web=8002, cron=no port
```

### Tasks

| # | Task | Files | Size | Status |
|---|------|-------|------|--------|
| **Docker Setup** | | | | |
| 4.1 | Update Dockerfile (Python 3.13, psycopg2 deps) | Dockerfile | S | DONE |
| 4.2 | Update docker-compose.yml (postgres:5433 + web:8002 + cron) | docker-compose.yml | S | DONE |
| 4.3 | Install psycopg2-binary + dj-database-url | requirements.txt | S | PENDING |
| 4.4 | Update settings.py for DATABASE_URL | settings.py | S | PENDING |
| **PostgreSQL Migration** | | | | |
| 4.5 | `docker compose up postgres` - start PG on port 5433 | - | S | PENDING |
| 4.6 | Build migrate_to_postgres command | management/commands/ | M | PENDING |
| 4.7 | Run `migrate` on PG (create schema) | - | S | PENDING |
| 4.8 | Run data migration (SQLite -> PG) + verify row counts | - | M | PENDING |
| 4.9 | Verify PG data integrity (admin, dry-run, check_replies) | - | M | PENDING |
| 4.10 | Run one real send cycle on PG | - | S | PENDING |
| **Full Docker** | | | | |
| 4.11 | `docker compose up` - all 3 services (postgres + web + cron) | - | S | PENDING |
| 4.12 | Verify cron container sends at 11am and monitors replies every 10min | - | M | PENDING |
| 4.13 | Update backup_to_gdrive.sh for pg_dump | backup_to_gdrive.sh | S | PENDING |
| **Cleanup** | | | | |
| 4.14 | Remove legacy Campaign.product CharField | models.py, migrations/ | M | PENDING |
| 4.15 | Refactor views.py to use services | views.py | M | PENDING |
| 4.16 | Refactor process_queue.py to use services | process_queue.py | M | PENDING |
| 4.17 | Update CLAUDE.md with Docker + PG architecture | CLAUDE.md | M | PENDING |
| 4.18 | Add deprecation notices to old sender scripts | bni-scraper/, google-maps-scraper/ | S | PENDING |
| 4.19 | Remove macOS crontab (replaced by Docker cron container) | - | S | PENDING |
| 4.20 | Keep SQLite as 30-day safety net | - | S | PENDING |

### Docker Architecture

```
docker compose up
    |
    +-- outreach_db (postgres:16-alpine)
    |   Port: 5433:5432
    |   Volume: pgdata
    |
    +-- outreach_web (Django)
    |   Port: 8002:8002
    |   DATABASE_URL -> postgres://outreach@postgres:5432/outreach
    |   Runs: migrate + runserver
    |
    +-- outreach_cron (same image, runs cron)
        No port exposed
        DATABASE_URL -> postgres://outreach@postgres:5432/outreach
        Runs:
          0 11 * * 1-5  send_sequences
          */10 * * * *   handle_replies
```

One command to start everything: `docker compose up -d`

### Sprint 4 Verification
```bash
# Docker
docker compose up -d
docker compose ps                        # all 3 services healthy
docker compose logs cron                 # cron jobs installed

# Data migration
docker compose exec web python manage.py migrate_to_postgres
docker compose exec web python manage.py send_sequences --dry-run --status
docker compose exec web python manage.py check_replies --dry-run

# Real send test
docker compose exec web python manage.py send_sequences --campaign "TaggIQ BNI" --limit 1

# Backup
./backup_to_gdrive.sh                   # verify pg_dump works
```

### Sprint 4 Rollback
- **Docker issue:** `docker compose down`, run Django locally with `venv/bin/python manage.py runserver 8002`
- **PostgreSQL issue:** Remove `DATABASE_URL` from .env, Django falls back to SQLite instantly
- **Both:** System reverts to pre-Sprint-4 state in 10 seconds

---

## Monitoring Checklist (2026-04-09 to 2026-04-15)

Check daily:
- [ ] /tmp/campaigns_daily.log - sends going out at 11am
- [ ] No errors or unexpected behavior
- [ ] Email counts match expected volumes per campaign
- [ ] Reply monitoring still works (check /tmp/taggiq_reply_monitor.log)
- [ ] No duplicate emails (spot check EmailLog)

If any issues: revert run_campaigns.sh to call old 3 scripts (10-second fix, old scripts still on disk).

---

## Key Files Created/Modified (for next session context)

### New files
```
campaigns/models.py               - Organization, Product, EmailTemplate, CallScript, PromptTemplate, AIUsageLog + modified Campaign, Suppression, ScriptInsight
campaigns/services/__init__.py
campaigns/services/eligibility.py  - get_eligible_prospects(), is_suppressed()
campaigns/services/safeguards.py   - daily_remaining(), check_min_gap(), can_send_to_prospect()
campaigns/services/template_resolver.py - get_template(), render(), determine_variant()
campaigns/services/send_orchestrator.py - send_one()
campaigns/services/ai_tracker.py   - log_ai_call(), get_prompt(), MODEL_PRICING
campaigns/management/commands/seed_templates.py  - one-time template seeding
campaigns/management/commands/send_sequences.py  - universal sender (replaces 18 scripts)
campaigns/migrations/0010_v2_multi_tenant_models.py
campaigns/migrations/0011_seed_org_products_link_fks.py
```

### Modified files
```
campaigns/admin.py          - registered all new models
campaigns/views.py          - product filters use product_ref__slug FK
campaigns/call_service.py   - reads from CallScript model with fallback
campaigns/management/commands/check_replies.py - product-scoped suppressions
run_campaigns.sh            - calls send_sequences instead of 3 scripts
```

### Untouched (deferred to Sprint 4)
```
campaigns/views.py outreach_send()     - still uses inline safeguards (API contract stable)
campaigns/management/commands/process_queue.py - still uses inline safeguards
campaigns/management/commands/analyze_calls.py - AI tracking not yet wired
outreach/settings.py                   - still SQLite
backup_to_gdrive.sh                    - still sqlite3 .backup
```

---

## Sprint 5: AWS Deployment - PLANNED

**Prerequisite:** Sprint 4 complete + 2 business days Docker cron verified
**Full plan:** `docs/aws-deployment-and-taggiq-integration.md`

Summary:
- Deploy Paperclip Docker stack to EC2 t3.micro (eu-west-1, same VPC as TaggIQ)
- Nginx + Let's Encrypt SSL at `outreach.taggiq.com`
- Data migration: local PostgreSQL dump -> AWS restore (~30 min downtime)
- Zero impact on current campaigns (sequence logic uses DB timestamps)
- Vapi webhook URL updated to public endpoint
- Local Mac no longer needed for 24/7 operation

---

## Sprint 6: TaggIQ Webhook Bridge - PLANNED

**Prerequisite:** Sprint 5 complete + 2 business days AWS cron verified
**Full plan:** `docs/aws-deployment-and-taggiq-integration.md`

Summary:
- WebhookEvent model + HMAC-verified endpoint in Paperclip
- Celery task + Django signals in TaggIQ fire lifecycle events
- 6 events: trial_started, supplier_connected, first_quote_created, trial_expiring, subscription_started, trial_expired
- 4 new lifecycle campaigns: Trial Activation, Trial Conversion, Trial Expiry, Win-Back
- Closes the gap between TaggIQ signup and paid conversion

---

## Future Backlog (NOT in Sprints 1-6)

| Item | When to do it | Trigger |
|------|--------------|---------|
| Auth/permissions middleware | First design partner onboards | Paul Rivers or Declan wants their own login |
| Tenant-scoped API auth (JWT) | Building dashboard frontend | Need remote API access |
| Per-org AI billing | Multiple orgs using AI replies | Design partners generating AI costs |
| Celery/Redis async jobs | Call volume exceeds cron capacity | >100 calls/day |
| FP Dublin B2B email sequences | After corporate prospect import | Emma's campaign ready to send |
| Seed PromptTemplate from skill files | First design partner | They need their own reply voice |
| Wire AI tracking into analyze_calls | Calling goes active | Need cost observability |
| Seed CallScript records | Calling campaigns activated | DB-driven call scripts |
| Paperclip as SME/BNI product | After 50 TaggIQ customers | Validated pipeline + demand from BNI members |
