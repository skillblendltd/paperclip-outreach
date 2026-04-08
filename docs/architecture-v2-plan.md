# Paperclip Outreach v2 - Architecture Refactoring Plan

**Date:** 2026-04-08
**Author:** Prakash Inani + Claude (CTO Architect + AI Architect)
**Status:** Approved for implementation

---

## Why This Refactoring

The outreach system is validated and running 3 products (TaggIQ, Fully Promoted, Kritno) across 13 campaigns. It works, but the architecture has accumulated debt that will block scaling:

- **No multi-tenancy** - can't onboard design partners as separate orgs
- **18 duplicate sender scripts** with hardcoded campaign IDs and templates - adding a campaign requires writing new Python code
- **Global suppression list** - an FP opt-out incorrectly blocks TaggIQ sends
- **SQLite database** - can't handle concurrent access needed for design partners or RDS deployment
- **Zero AI observability** - no token tracking, no cost allocation, no prompt versioning
- **Duplicated safeguard logic** across views.py, process_queue.py, and sender scripts
- **Hardcoded call scripts** in Python instead of DB-configurable

**Target state:** Multi-tenant SaaS where adding a new org/campaign = DB records only, zero code changes. PostgreSQL for multi-user access and AWS RDS deployment. Full AI cost tracking per org.

---

## Data Model - Multi-Tenant Hierarchy

```
Organization                          # "Skillblend Ltd", "Print RFT", etc.
    -> Product                        # "TaggIQ", "Fully Promoted Ireland"
        -> Campaign                   # "TaggIQ BNI Ireland", "FP Dublin B2B"
            -> Prospect
            -> EmailLog / CallLog
            -> EmailTemplate
            -> MailboxConfig
        -> Suppression (scoped to product, not global)
        -> CallScript
        -> PromptTemplate (AI prompts per product)
    -> AIUsageLog (cost tracking per org)
```

Every query chain starts from Organization. Design partners only see their own org's data.

---

## Target Directory Structure

```
paperclip-outreach/
    campaigns/
        models.py                    MODIFIED  (+ Organization, Product, EmailTemplate, CallScript,
                                               PromptTemplate, AIUsageLog, Campaign send window fields,
                                               Campaign.product FK, Suppression product FK)
        views.py                     MODIFIED  (delegate safeguards to services)
        admin.py                     MODIFIED  (+ all new model admin registrations)
        email_service.py             UNCHANGED
        call_service.py              MODIFIED  (read first_messages from CallScript model)
        urls.py                      MODIFIED  (+ new API endpoints)
        forms.py                     UNCHANGED
        services/                    NEW
            __init__.py              NEW
            eligibility.py           NEW  (prospect eligibility + suppression checks)
            safeguards.py            NEW  (daily limits, min gap, per-prospect checks)
            template_resolver.py     NEW  (DB template lookup, A/B variant, variable rendering)
            send_orchestrator.py     NEW  (core send-one-email function)
            ai_tracker.py            NEW  (AI usage logging + cost calculation)
        management/commands/
            send_sequences.py        NEW  (universal sender - replaces 18 scripts)
            seed_templates.py        NEW  (one-time: seed EmailTemplate from hardcoded scripts)
            seed_org_products.py     NEW  (one-time: create Skillblend org + 3 products, migrate FKs)
            migrate_to_postgres.py   NEW  (one-time: SQLite to PostgreSQL data copy)
            check_replies.py         MODIFIED  (use product-scoped suppression)
            process_queue.py         MODIFIED  (use services for safeguards)
            place_calls.py           MODIFIED  (use CallScript model)
            analyze_calls.py         MODIFIED  (log AI usage, read PromptTemplate)
            send_campaign.py         UNCHANGED (keep as manual fallback)
            review_replies.py        UNCHANGED
            seed_reply_templates.py  UNCHANGED
        migrations/
            0010_organization_product.py                        NEW
            0011_emailtemplate_callscript_campaign_windows.py   NEW
            0012_prompttemplate_aiusagelog.py                    NEW
            0013_suppression_product_fk.py                      NEW
            0014_campaign_product_fk.py                         NEW (data migration)

    outreach/
        settings.py                  MODIFIED  (DATABASE_URL support via dj-database-url)

    requirements.txt                 MODIFIED  (+ psycopg2-binary, dj-database-url, pytz)
    docker-compose.yml               MODIFIED  (+ postgres service)
    run_campaigns.sh                 MODIFIED  (Phase 5: call send_sequences instead of 3 scripts)
    backup_to_gdrive.sh              MODIFIED  (Phase 6: pg_dump instead of sqlite3 .backup)
    CLAUDE.md                        MODIFIED  (update architecture docs)

    bni-scraper/                     Scrapers UNCHANGED, sender scripts DEPRECATED (not deleted)
    google-maps-scraper/             Scrapers UNCHANGED, sender scripts DEPRECATED (not deleted)
    fp-ireland-master/               Importer UNCHANGED, sender scripts DEPRECATED (not deleted)
```

---

## New & Modified Models

### Organization (NEW)

Top-level tenant. All data is scoped through this.

```
Fields:
    name            "Skillblend Ltd"
    slug            "skillblend" (unique, URL-safe)
    owner           FK to Django User (nullable for now)
    is_active       default True

    db_table: 'organizations'
```

### Product (NEW)

Replaces Campaign.product CharField. One org can have multiple products.

```
Fields:
    organization    FK to Organization
    name            "TaggIQ"
    slug            "taggiq" (unique within org)
    is_active       default True

    unique_together: (organization, slug)
    db_table: 'products'
```

Initial data migration creates:
- Organization "Skillblend Ltd" (slug: skillblend)
- Product "TaggIQ" (slug: taggiq, org: skillblend)
- Product "Fully Promoted Ireland" (slug: fullypromoted, org: skillblend)
- Product "Kritno" (slug: kritno, org: skillblend)

### Campaign (MODIFIED)

```
Changed fields:
    product         FK to Product     <-- replaces CharField(choices=[...])

New fields:
    send_window_timezone    default 'Europe/Dublin'
    send_window_start_hour  default 10
    send_window_end_hour    default 17
    send_window_days        default '0,1,2,3,4' (Mon-Fri, comma-separated)
    batch_size              default 100 (max prospects per run)
    inter_send_delay_min    default 5 (seconds between sends)
    inter_send_delay_max    default 60 (seconds between sends)
    priority_cities         default '' (comma-separated, e.g. 'dublin,cork')
```

Data migration: maps existing CharField values to Product FKs (taggiq -> Product "TaggIQ", etc.)

### EmailTemplate (NEW)

One row per campaign + sequence + variant. Replaces all hardcoded templates in sender scripts.

```
Fields:
    campaign          FK to Campaign
    sequence_number   1-5
    ab_variant        'A' or 'B'
    subject_template  e.g. "quick question about {{COMPANY}}"
    body_html_template  Full HTML body with {{FNAME}}, {{COMPANY}}, {{CITY}}, {{YEAR}}, {{SEGMENT}}
    template_name     Identifier logged in EmailLog (e.g. "bni_seq1_peer_A")
    sequence_label    Human label (e.g. "Peer Story", "Design Partner", "Breakup")
    is_active         Toggle on/off

    unique_together: (campaign, sequence_number, ab_variant)
    db_table: 'email_templates'
```

Total: ~130 rows (13 campaigns x 5 sequences x 2 variants).

### CallScript (NEW)

Per-segment first message for Vapi calls. Replaces hardcoded first_messages dict in call_service.py.

```
Fields:
    campaign       FK to Campaign
    segment        'signs', 'apparel_embroidery', 'print_shop', etc. (empty = default)
    first_message  Full Vapi first_message text
    is_active      Toggle on/off

    unique_together: (campaign, segment)
    db_table: 'call_scripts'
```

### PromptTemplate (NEW)

DB-managed AI prompts. Replaces hardcoded Claude skill prompts for multi-tenant customization.

```
Fields:
    product         FK to Product
    feature         'email_reply' | 'call_analysis' | 'script_improvement'
    name            "TaggIQ Email Expert v3"
    system_prompt   TextField (the full prompt)
    model           default 'claude-sonnet-4-6'
    max_tokens      default 4096
    temperature     default 0.7
    is_active       bool
    version         IntegerField (auto-increment per product+feature)

    db_table: 'prompt_templates'
```

How it works:
- Reply monitor checks PromptTemplate first for the campaign's product
- If found and active: uses DB prompt with specified model
- If not found: falls back to Claude skill file (/taggiq-email-expert, /fp-email-expert)
- Design partners configure their own reply voice via admin
- Version field enables A/B testing of prompts

### AIUsageLog (NEW)

Tracks every AI call for cost allocation and observability.

```
Fields:
    organization    FK to Organization
    product         FK to Product
    campaign        FK to Campaign (nullable)
    prospect        FK to Prospect (nullable)
    feature         'email_reply' | 'call_analysis' | 'script_improvement' | 'classification'
    model           'claude-sonnet-4-6' | 'claude-haiku-4-5' etc.
    input_tokens    int
    output_tokens   int
    cost_usd        DecimalField(max_digits=8, decimal_places=4)
    latency_ms      int
    success         bool
    error_message   TextField (blank, if failed)
    prompt_version  int (links to PromptTemplate.version, nullable)

    db_table: 'ai_usage_log'
    indexes: [organization+created_at], [product+feature], [created_at]
```

Cost calculation (in ai_tracker service):
```
MODEL_PRICING = {
    'claude-sonnet-4-6':  {'input': 3.00/1M, 'output': 15.00/1M},
    'claude-haiku-4-5':   {'input': 0.80/1M, 'output': 4.00/1M},
    'claude-opus-4-6':    {'input': 15.00/1M, 'output': 75.00/1M},
}
```

### Suppression (MODIFIED - product-scoped)

```
Changed fields:
    email     EmailField (remove unique=True)
    product   FK to Product (nullable, blank=True)   <-- null = global block

    unique_together: (email, product)

    Check logic: suppressed if (email match) AND (product IS NULL OR product = campaign.product)
```

Data migration: all existing rows get `product=NULL` (global) - preserves current behavior exactly.

### ScriptInsight (MODIFIED - learning loop tracking)

```
New fields:
    baseline_answer_rate      FloatField (rate BEFORE prompt change, nullable)
    baseline_interest_rate    FloatField (nullable)
    post_change_answer_rate   FloatField (measured 1 week after, nullable)
    post_change_interest_rate FloatField (nullable)
    improvement_measured      BooleanField default False
    measured_at               DateTimeField (nullable)
```

Enables: "Last week's prompt change improved interest_rate from 12% to 18%."

---

## Service Layer (campaigns/services/)

### eligibility.py

Consolidated from: bni send_sequence.py, google-maps send_ireland_sequences.py, fp send_campaign.py

```
get_eligible_prospects(campaign) -> list of (Prospect, next_sequence_number)
    Seq 1: status='new', emails_sent=0, has email
    Seq 2-5: status='contacted', 7-day gap from last email
    Excludes: opted_out, not_interested, interested, engaged, demo_scheduled, design_partner

is_suppressed(email, product) -> bool
    Product-scoped suppression check (product FK, null = global)
```

### safeguards.py

Consolidated from: views.py lines 63-154, process_queue.py lines 76-170

```
daily_remaining(campaign) -> int
check_min_gap(campaign) -> (ok, wait_seconds)
can_send_to_prospect(campaign, prospect, seq_num) -> (ok, reason)
    Checks: send_enabled, status, suppression, max per prospect, sequence order, duplicate
```

### template_resolver.py

Consolidated from: all sender scripts' template dicts + views.py variable rendering

```
get_template(campaign, seq_num, prospect) -> EmailTemplate or None
render(template, prospect, campaign) -> (subject, body_html)
determine_variant(prospect) -> 'A' or 'B'
    Standardized on hash(prospect.id) % 2 (already used by API)
```

### send_orchestrator.py

Consolidated from: views.py outreach_send, process_queue.py send logic

```
send_one(campaign, prospect, template, seq_num, dry_run=False) -> dict
    Render template, send via EmailService, log to EmailLog, update prospect status
    Returns {status, log_id, error}
```

### ai_tracker.py (NEW)

AI usage logging and cost calculation.

```
log_ai_call(campaign, prospect, feature, model, input_tokens, output_tokens,
            latency_ms, success, error_message='', prompt_version=None) -> AIUsageLog
    Calculates cost_usd from MODEL_PRICING dict
    Resolves organization and product from campaign FK chain
    Returns the created AIUsageLog record

get_usage_summary(organization, date_from, date_to) -> dict
    Returns: total_cost, by_product, by_feature, total_calls, error_rate

get_prompt(product, feature) -> PromptTemplate or None
    Returns active prompt for this product+feature, or None (fall back to skill file)
```

---

## AI Architecture

### Current AI Touchpoints

| # | Feature | Model | Trigger | Tokens/call | Frequency |
|---|---------|-------|---------|-------------|-----------|
| 1 | Email reply generation | Claude Sonnet (CLI) | Every 10min cron | ~2K-4K | ~5-20/day |
| 2 | Call transcript analysis | Claude via Bedrock | Manual/periodic | ~5K-15K | ~1/week |
| 3 | Vapi outbound calls | Vapi's built-in LLM | place_calls cron | Vapi-managed | Not active yet |
| 4 | Auto-learning loop | Claude via Bedrock | analyze_calls | ~10K-20K | ~1/week |
| 5 | Email classification | Rule-based keywords | check_replies cron | 0 (no AI) | Every 10min |

### Model Selection Per Use Case

| Task | Current | Recommended | Why |
|------|---------|------------|-----|
| Email reply generation | Sonnet | Sonnet | Quality matters for customer-facing |
| Email classification | Rules | Rules (keep) | Works perfectly, zero cost |
| Call transcript analysis | Sonnet | Sonnet | Long context, quality matters |
| Simple data extraction | Sonnet | Haiku | 10x cheaper for structured extraction |
| Reply classification (future) | Rules | Haiku | When keyword rules miss nuance |

### Multi-Tenant AI Isolation Rules

1. Reply generation prompts must ONLY include the current org's prospect data and email history
2. Call analysis must ONLY analyze the current org's transcripts
3. PromptTemplates are per-product (per-org by extension)
4. AIUsageLog is always scoped to organization - enables per-org billing
5. When pulling "similar past replies" for context, ALWAYS filter by organization FK chain

### Cost Projections

**Current scale (1 org, 3 products):**

| Feature | Calls/month | Tokens/call | Cost/month |
|---------|-------------|-------------|-----------|
| Email replies | ~300 | ~3K | ~$4.50 |
| Call analysis | ~4 | ~15K | ~$0.90 |
| Script improvement | ~4 | ~20K | ~$1.20 |
| **Total** | | | **~$6.60/mo** |

**At 10 design partners (10 orgs, ~30 products):**

| Feature | Calls/month | Tokens/call | Cost/month |
|---------|-------------|-------------|-----------|
| Email replies | ~3,000 | ~3K | ~$45 |
| Call analysis | ~40 | ~15K | ~$9 |
| Script improvement | ~40 | ~20K | ~$12 |
| **Total** | | | **~$66/mo** |

### Learning Loop Tracking

The analyze_calls command generates ScriptInsight records with suggested prompt improvements. With the new fields, the loop becomes measurable:

```
Week 1: analyze_calls -> ScriptInsight (baseline_answer_rate=35%, suggestions="...")
         -> Push new prompt to Vapi (prompt_applied=True)
Week 2: Cron measures post_change_answer_rate=42%
         -> improvement_measured=True
         -> Decision: keep new prompt (7% improvement)
```

---

## Universal Sender Command (send_sequences.py)

Replaces 18 sender scripts with one DB-driven command:

```bash
python manage.py send_sequences                      # all active campaigns
python manage.py send_sequences --product taggiq     # one product (by slug)
python manage.py send_sequences --campaign "BNI"     # name substring match
python manage.py send_sequences --dry-run            # preview only
python manage.py send_sequences --status             # show eligible counts, no send
```

Logic flow:
1. Get campaigns: Campaign.objects.filter(sending_enabled=True, product__is_active=True, product__organization__is_active=True)
2. For each campaign, check send window (timezone-aware day/hour from Campaign fields)
3. Get daily remaining from safeguards service
4. Get eligible prospects from eligibility service
5. Sort by priority cities, then score descending
6. Batch limit: campaign.batch_size
7. For each prospect: resolve template from EmailTemplate -> render -> send via orchestrator
8. Random delay between sends: randint(inter_send_delay_min, inter_send_delay_max)
9. Log summary per campaign

Safe to run multiple times - API duplicate check prevents same sequence sent twice.

---

## PostgreSQL Migration

### settings.py change:

```python
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db" / "outreach.sqlite3"}'
    )
}
```

No DATABASE_URL in .env = SQLite (current behavior). Set DATABASE_URL = instant switch to PG.

### Data migration steps:

1. PostgreSQL 14 already installed via Homebrew
2. `createdb outreach`
3. Add `DATABASE_URL=postgres://pinani@localhost/outreach` to .env
4. `python manage.py migrate` (creates schema on PG)
5. `python manage.py migrate_to_postgres` (reads SQLite, writes PG, verifies row counts)
6. Run `send_sequences --dry-run --status` to verify
7. Keep SQLite file for 30 days as safety net

### backup_to_gdrive.sh change:

```bash
# Replace:  sqlite3 "$DB_SRC" ".backup '$DB_DEST'"
# With:     pg_dump outreach > "$BACKUP_DIR/db/outreach_${TODAY}.sql"
```

---

## Implementation Phases

### Phase 1: Organization + Product Models + Data Migration

**What:** Add Organization, Product models. Migrate Campaign.product CharField to Product FK. Migrate Suppression to product FK.
**Files:** models.py, admin.py, 3 migrations (schema + data), seed_org_products.py
**Risk:** Low - FK migration needs careful data migration step
**Test:**
  - `python manage.py migrate`
  - Verify all 13 campaigns have correct Product FK
  - Verify `campaign.product.slug` returns same value as old CharField
  - Verify `campaign.product.organization.name` returns "Skillblend Ltd"
  - Browse admin - all existing data intact
**Rollback:** `python manage.py migrate campaigns 0009`

### Phase 2: EmailTemplate + CallScript + Campaign Send Windows

**What:** Add EmailTemplate, CallScript models. Add Campaign send window fields.
**Files:** models.py, admin.py, 1 migration
**Risk:** Zero - additive only, nothing reads new models yet
**Test:** `python manage.py migrate`, browse admin
**Rollback:** Reverse migration

### Phase 3: AI Models (PromptTemplate + AIUsageLog + ScriptInsight updates)

**What:** Add PromptTemplate, AIUsageLog. Add learning loop fields to ScriptInsight.
**Files:** models.py, admin.py, services/ai_tracker.py, 1 migration
**Risk:** Zero - additive only
**Test:** `python manage.py migrate`, create test PromptTemplate in admin, verify ai_tracker service calculates cost correctly
**Rollback:** Reverse migration

### Phase 4: Service Layer Extraction

**What:** Create campaigns/services/ with eligibility, safeguards, template_resolver, send_orchestrator
**Files:** 5 new files in campaigns/services/
**Risk:** Zero - services exist but nothing calls them yet
**Test:** Import each service in Django shell, call with dry-run semantics, compare against existing script output
**Rollback:** Delete services/ directory

### Phase 5: Seed Templates + Universal Sender + Wire Services + Cut Over Cron

**What:** Populate EmailTemplate from hardcoded scripts. Build send_sequences command. Refactor views.py/process_queue.py/check_replies.py to use services. Switch cron.
**Files:** seed_templates.py, send_sequences.py, views.py, process_queue.py, check_replies.py, call_service.py, place_calls.py, run_campaigns.sh
**Risk:** Medium - changing live code paths
**Test:**
  - `python manage.py seed_templates --all` - verify ~130 templates in admin
  - `python manage.py send_sequences --dry-run` - compare eligible counts against old scripts
  - Send 1 real email per campaign via new command
  - Run old scripts AND new command in parallel for 1 day
  - Switch cron, monitor /tmp/campaigns_daily.log for 1 week
**Rollback:** Revert run_campaigns.sh (10 seconds). Old scripts still on disk.

### Phase 6: PostgreSQL Migration

**What:** Switch database from SQLite to PostgreSQL
**Files:** settings.py, requirements.txt, docker-compose.yml, .env, backup_to_gdrive.sh, migrate_to_postgres.py
**Risk:** Low - instant rollback by removing DATABASE_URL from .env
**Test:**
  - Row count comparison (all tables including new ones)
  - Admin browse-through
  - send_sequences --dry-run on PG
  - check_replies --dry-run on PG
  - One real send cycle
**Rollback:** Remove DATABASE_URL from .env - instant fallback to SQLite

### Phase 7: Cleanup + Docs

**What:** Update CLAUDE.md, mark old sender scripts deprecated (NOT deleted)
**Files:** CLAUDE.md, deprecation notices
**Risk:** Zero

---

## Zero-Downtime Guarantee

| Phase | Cron at 11am | Reply monitor (every 10min) | Risk |
|-------|-------------|---------------------------|------|
| 1-3 | Old scripts (unchanged) | check_replies (unchanged) | None |
| 4 | Old scripts (unchanged) | check_replies (unchanged) | None |
| 5 | New send_sequences | check_replies (uses services) | Low - revert in 10s |
| 6 | send_sequences on PG | check_replies on PG | Low - revert by env var |

**Rule:** Only ONE thing changes per phase. Never change the sender AND the database simultaneously.

**Phase 6 timing:** Run data migration at night (after 11pm backup, before 11am send). Switch DATABASE_URL. Morning cron hits PG. If anything wrong, remove DATABASE_URL before next cron run.

---

## Verification Checklist (run after each phase)

- [ ] `python manage.py check` - no errors
- [ ] Django admin loads, all models browsable
- [ ] `campaign.product.organization.name` returns correct org for all campaigns
- [ ] `send_sequences --dry-run --status` - correct campaign/prospect counts
- [ ] `check_replies --dry-run` - connects to all mailboxes
- [ ] Existing prospect data intact (spot check 5 random prospects)
- [ ] Email history intact (spot check recent EmailLog entries)
- [ ] No duplicate emails sent (check EmailLog for same prospect + sequence)
- [ ] AI usage log records created for test AI calls (Phase 3+)

---

## Key Files Reference

| File | Lines | Role in refactoring |
|------|-------|-------------------|
| campaigns/models.py | 448 | Add 4 new models, modify 3 existing models |
| campaigns/views.py | 977 | Extract lines 63-154 (safeguards) to services, update product filters |
| campaigns/admin.py | 733 | Register Organization, Product, EmailTemplate, CallScript, PromptTemplate, AIUsageLog |
| campaigns/email_service.py | 267 | UNCHANGED - already clean |
| campaigns/call_service.py | 110 | Remove hardcoded first_messages, read from CallScript |
| check_replies.py | 658 | Update suppression checks for product-scoped FK |
| process_queue.py | 257 | Replace inline safeguards with service calls |
| analyze_calls.py | 284 | Log AI usage via ai_tracker, read PromptTemplate, measure learning loop |
| bni-scraper/send_sequence.py | 559 | SOURCE for BNI template content (lines 72-193) |
| google-maps-scraper/send_ireland_sequences.py | 545 | SOURCE for Ireland template content + eligibility logic |
| google-maps-scraper/send_london_sequences.py | 539 | SOURCE for London template content |
| fp-ireland-master/send_campaign.py | 411 | SOURCE for FP template content |
| outreach/settings.py | 95 | DB config change (lines 50-55) |
| run_campaigns.sh | 73 | Switch to call send_sequences |
| backup_to_gdrive.sh | 81 | Switch sqlite3 .backup to pg_dump |

---

## What We Are NOT Building Yet

These are future concerns, not Phase 1-7 scope:

- **Auth/permissions middleware** - not needed while Prakash is the only user. Add when first design partner onboards.
- **Tenant-scoped API auth (JWT/session)** - current API is local-only. Add when building dashboard frontend.
- **Per-org billing for AI usage** - AIUsageLog tracks cost, but billing integration is future.
- **Separate databases per tenant** - single PostgreSQL with org FK filtering is fine for hundreds of tenants.
- **Celery/Redis for async jobs** - cron works fine at current scale. Add when call volume requires real-time processing.
- **RAG/vector search** - not needed for structured outreach data. All queries are FK-based.
