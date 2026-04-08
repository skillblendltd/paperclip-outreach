# Paperclip Outreach v2 - Sprint Implementation Plan

**Date:** 2026-04-08
**Reference:** docs/architecture-v2-plan.md
**Approach:** 4 sprints, each ~1 session (2-4 hours). Each sprint is independently shippable.

---

## Sprint 1: Foundation (Multi-Tenant Models + DB Setup)

**Goal:** Establish the Organization -> Product -> Campaign hierarchy and all new models. Zero behavior changes to running system.

### Tasks

| # | Task | Files | Size | Acceptance Criteria |
|---|------|-------|------|-------------------|
| 1.1 | Create Organization model | models.py | S | Model with name, slug, owner(nullable), is_active. db_table='organizations' |
| 1.2 | Create Product model | models.py | S | FK to Organization, name, slug, is_active. unique_together=(organization, slug). db_table='products' |
| 1.3 | Add Campaign.product FK (keep old CharField temporarily) | models.py | S | New field `product_ref` FK to Product, nullable. Old `product` CharField untouched. |
| 1.4 | Create EmailTemplate model | models.py | S | FK Campaign, sequence_number, ab_variant, subject_template, body_html_template, template_name, sequence_label, is_active. unique_together=(campaign, sequence_number, ab_variant) |
| 1.5 | Create CallScript model | models.py | S | FK Campaign, segment, first_message, is_active. unique_together=(campaign, segment) |
| 1.6 | Create PromptTemplate model | models.py | S | FK Product, feature, name, system_prompt, model, max_tokens, temperature, is_active, version |
| 1.7 | Create AIUsageLog model | models.py | S | FKs to Organization/Product/Campaign/Prospect (nullable), feature, model, input_tokens, output_tokens, cost_usd, latency_ms, success, error_message, prompt_version |
| 1.8 | Add Campaign send window fields | models.py | S | send_window_timezone, start_hour, end_hour, send_days, batch_size, inter_send_delay_min/max, priority_cities |
| 1.9 | Modify Suppression model | models.py | S | Add product FK (nullable). Change unique to unique_together=(email, product). |
| 1.10 | Add ScriptInsight learning loop fields | models.py | S | baseline_answer_rate, baseline_interest_rate, post_change_answer_rate, post_change_interest_rate, improvement_measured, measured_at |
| 1.11 | Generate migrations | migrations/ | S | makemigrations, verify migration files look correct |
| 1.12 | Create seed_org_products command | management/commands/ | M | Creates Skillblend org + 3 products. Maps existing Campaign.product CharField to product_ref FK. Maps Suppression product CharField to FK. |
| 1.13 | Register all new models in admin | admin.py | M | Organization, Product, EmailTemplate (inline preview), CallScript, PromptTemplate, AIUsageLog (read-only). Product shown with org filter. |
| 1.14 | Run migrations + seed data | - | S | `migrate` + `seed_org_products`. Verify all 13 campaigns have correct product_ref FK. |
| 1.15 | Swap Campaign.product to FK | models.py, migrations/ | M | Remove old CharField, rename product_ref to product. Data migration to preserve values. Update all code references from `campaign.product` (string) to `campaign.product.slug` or `campaign.product` (FK). |
| 1.16 | Update views.py product filters | views.py | M | Change `filter(product='taggiq')` to `filter(product__slug='taggiq')`. Update dashboard, prospects, calls, script-insights endpoints. |
| 1.17 | Verify everything works | - | S | Admin loads, all endpoints return 200, check_replies --dry-run passes, existing cron unaffected |

### Sprint 1 Verification
```bash
python manage.py migrate
python manage.py seed_org_products
python manage.py check
# Browse admin - verify Organization, Product, all campaigns linked
# Verify: campaign.product.organization.name == "Skillblend Ltd" for all campaigns
python manage.py check_replies --dry-run
# Hit API endpoints, verify product filter still works
curl http://localhost:8002/api/dashboard/?product=taggiq
```

### Sprint 1 Rollback
```bash
python manage.py migrate campaigns 0009  # reverts all new migrations
```

---

## Sprint 2: Service Layer + Universal Sender

**Goal:** Build the service layer and universal sender command. Old scripts still run via cron - new code runs alongside for testing.

### Tasks

| # | Task | Files | Size | Acceptance Criteria |
|---|------|-------|------|-------------------|
| 2.1 | Create services/__init__.py | services/ | S | Empty init |
| 2.2 | Build eligibility.py | services/eligibility.py | M | `get_eligible_prospects(campaign)` returns (prospect, next_seq) list. Seq 1: new+no emails. Seq 2-5: contacted+7-day gap. Excludes terminal statuses. |
| 2.3 | Build safeguards.py | services/safeguards.py | M | `daily_remaining(campaign)`, `check_min_gap(campaign)`, `can_send_to_prospect(campaign, prospect, seq)`. Extracted from views.py lines 63-154 and process_queue.py lines 76-170. |
| 2.4 | Build template_resolver.py | services/template_resolver.py | M | `get_template(campaign, seq, prospect)` from EmailTemplate model. `render(template, prospect, campaign)` with variable substitution. `determine_variant(prospect)` via hash. |
| 2.5 | Build send_orchestrator.py | services/send_orchestrator.py | M | `send_one(campaign, prospect, template, seq, dry_run)` - render, send via EmailService, log to EmailLog, update prospect status. Single authoritative send path. |
| 2.6 | Build ai_tracker.py | services/ai_tracker.py | S | `log_ai_call(...)` with cost calculation. `get_prompt(product, feature)` for DB prompt lookup. MODEL_PRICING dict. |
| 2.7 | Verify services in Django shell | - | S | Import each service, call against real data with dry-run, compare eligible counts against old script output. |
| 2.8 | Build seed_templates command | management/commands/seed_templates.py | L | Reads hardcoded templates from bni send_sequence.py (lines 72-193), ireland send_ireland_sequences.py (lines 77-323), london send_london_sequences.py, fp send_campaign.py. Creates ~130 EmailTemplate rows. Idempotent (skip existing). |
| 2.9 | Run seed_templates, verify in admin | - | S | `seed_templates --all`. Browse admin, verify subject+body matches hardcoded scripts for each campaign/seq/variant. |
| 2.10 | Build send_sequences command | management/commands/send_sequences.py | L | Universal sender using all services. Supports --product, --campaign, --dry-run, --status flags. Checks send windows, rate limits, eligibility. Logs summary per campaign. |
| 2.11 | Parallel test: old vs new | - | M | Run `send_sequences --dry-run --status` and compare eligible counts against old scripts' dry-run output. Must match exactly. |
| 2.12 | Send 1 real email per campaign via new command | - | S | `send_sequences --campaign "TaggIQ BNI" --dry-run` then remove --dry-run with --limit 1. Verify email received correctly. |

### Sprint 2 Verification
```bash
python manage.py seed_templates --all
python manage.py send_sequences --dry-run --status
# Compare eligible counts with:
#   venv/bin/python bni-scraper/send_sequence.py --dry-run
#   venv/bin/python google-maps-scraper/send_ireland_sequences.py --dry-run
# Send 1 test email:
python manage.py send_sequences --campaign "TaggIQ BNI" --limit 1
```

### Sprint 2 Rollback
Delete campaigns/services/ directory and new management commands. Old scripts unaffected.

---

## Sprint 3: Wire Services + Cut Over Cron

**Goal:** Refactor existing code to use services. Switch cron from 3 old scripts to 1 universal sender.

### Tasks

| # | Task | Files | Size | Acceptance Criteria |
|---|------|-------|------|-------------------|
| 3.1 | Refactor views.py outreach_send() | views.py | M | Replace inline safeguard checks (lines 63-154) with calls to safeguards.daily_remaining(), safeguards.check_min_gap(), safeguards.can_send_to_prospect(). Use send_orchestrator for sending. API contract unchanged. |
| 3.2 | Refactor process_queue.py | process_queue.py | M | Replace duplicated safeguard checks (lines 76-170) with service calls. Use send_orchestrator for send+log+update. |
| 3.3 | Refactor check_replies.py suppression | check_replies.py | S | Update _execute_actions() to create Suppression with product FK instead of global. Update suppression check to use eligibility.is_suppressed(email, product). |
| 3.4 | Refactor call_service.py | call_service.py | S | Remove hardcoded first_messages dict. Read from CallScript model. Fallback to generic message if no CallScript found. |
| 3.5 | Seed CallScript records | - | S | Create CallScript rows for existing 4 segments (signs, apparel_embroidery, print_shop, promo_distributor). |
| 3.6 | Refactor place_calls.py | place_calls.py | S | Use CallScript from DB via updated call_service. |
| 3.7 | Wire AI tracking into analyze_calls | analyze_calls.py | S | Log AI usage via ai_tracker.log_ai_call(). Read prompt from PromptTemplate if available. Add ScriptInsight baseline fields. |
| 3.8 | Run full parallel test | - | M | Run old cron scripts at 11am. Run send_sequences at 11:05am. Compare log output. No duplicate sends (API prevents). |
| 3.9 | Update run_campaigns.sh | run_campaigns.sh | S | Replace 3 script calls with single `python manage.py send_sequences`. Keep lock file, logging, notification. |
| 3.10 | Monitor for 1 week | - | - | Check /tmp/campaigns_daily.log daily. Verify email counts match expectations. Watch for errors. |

### Sprint 3 Verification
```bash
# Before cutover - parallel run:
python manage.py send_sequences --dry-run --status  # compare with old scripts
# After cutover:
cat /tmp/campaigns_daily.log | tail -50  # verify sends going out
python manage.py check_replies --dry-run  # verify suppression scoping works
# Verify API still works:
curl http://localhost:8002/api/status/?campaign_id=64ed1454-18fc-4783-9438-da18143f7312
```

### Sprint 3 Rollback
Revert run_campaigns.sh to call old 3 scripts (10-second change). Old scripts still on disk and functional.

---

## Sprint 4: PostgreSQL Migration + Cleanup

**Goal:** Migrate from SQLite to PostgreSQL. Update backup script. Clean up docs.

### Tasks

| # | Task | Files | Size | Acceptance Criteria |
|---|------|-------|------|-------------------|
| 4.1 | Install psycopg2-binary + dj-database-url | requirements.txt | S | `pip install psycopg2-binary dj-database-url`, add to requirements.txt |
| 4.2 | Update settings.py for DATABASE_URL | settings.py | S | `dj_database_url.config(default=sqlite:///...)`. No DATABASE_URL = SQLite (backward compatible). |
| 4.3 | Update docker-compose.yml | docker-compose.yml | S | Add postgres service (postgres:16-alpine, port 5432, pgdata volume). |
| 4.4 | Create local PostgreSQL database | - | S | `brew services start postgresql@14` + `createdb outreach` |
| 4.5 | Build migrate_to_postgres command | management/commands/migrate_to_postgres.py | M | Reads all tables from SQLite (hardcoded path). Writes to current default DB (PG). Preserves UUIDs, timestamps. Verifies row counts match. Prints comparison report. |
| 4.6 | Set DATABASE_URL + run migrate | .env | S | `DATABASE_URL=postgres://pinani@localhost/outreach`. `python manage.py migrate` on PG. |
| 4.7 | Run data migration | - | M | `python manage.py migrate_to_postgres`. Verify row counts for all tables (campaigns, prospects, email_log, call_log, inbound_emails, email_queue, suppressions, mailbox_configs, reply_templates, script_insights, email_templates, call_scripts, prompt_templates, ai_usage_log, organizations, products). |
| 4.8 | Verify PG data integrity | - | M | Spot check 10 random prospects. Verify email history. Run send_sequences --dry-run --status. Run check_replies --dry-run. Browse admin. |
| 4.9 | Run one real send cycle on PG | - | S | `send_sequences --campaign "TaggIQ BNI" --limit 1`. Verify email sent and logged in PG. |
| 4.10 | Update backup_to_gdrive.sh | backup_to_gdrive.sh | S | Replace `sqlite3 .backup` with `pg_dump outreach > outreach_${TODAY}.sql`. Update rclone upload to use .sql file. |
| 4.11 | Update CLAUDE.md | CLAUDE.md | M | Update stack description, campaign table, API endpoints, new models, new commands, backup procedure. |
| 4.12 | Add deprecation notices to old scripts | bni-scraper/, google-maps-scraper/, fp-ireland-master/ | S | Add comment block at top of each deprecated sender script: "DEPRECATED - replaced by `python manage.py send_sequences`" |
| 4.13 | Keep SQLite as 30-day safety net | - | S | Do NOT delete db/outreach.sqlite3. Set calendar reminder for 30 days to remove. |

### Sprint 4 Verification
```bash
# Data migration verification:
python manage.py migrate_to_postgres  # shows row count comparison
python manage.py send_sequences --dry-run --status  # on PG
python manage.py check_replies --dry-run  # on PG
# Real send test:
python manage.py send_sequences --campaign "TaggIQ BNI" --limit 1
# Backup test:
./backup_to_gdrive.sh  # verify pg_dump works
```

### Sprint 4 Rollback
Remove `DATABASE_URL` from .env. System instantly falls back to SQLite. No data loss.

---

## Sprint Summary

| Sprint | Focus | Risk | Duration | Prerequisite |
|--------|-------|------|----------|-------------|
| 1 | Multi-tenant models + data migration | Low | 1 session | None |
| 2 | Service layer + universal sender | Low | 1 session | Sprint 1 |
| 3 | Wire services + cut over cron | Medium | 1 session + 1 week monitoring | Sprint 2 |
| 4 | PostgreSQL + cleanup | Low | 1 session + 30 day SQLite retention | Sprint 3 stable |

---

## What Remains After Sprint 4 (Future Backlog)

These are NOT in scope for Sprints 1-4:

| Item | When to do it | Trigger |
|------|--------------|---------|
| Auth/permissions middleware | First design partner onboards | Paul Rivers or Declan wants their own login |
| Tenant-scoped API auth (JWT) | Building dashboard frontend | Need remote API access |
| Per-org AI billing | Multiple orgs using AI replies | Design partners generating AI costs |
| Celery/Redis async jobs | Call volume exceeds cron capacity | >100 calls/day |
| Deploy to AWS RDS | Ready for production hosting | Moving off local machine |
| FP Dublin B2B email sequences | After corporate prospect import | Emma's campaign ready to send |
| Seed PromptTemplate from skill files | First design partner | They need their own reply voice |

---

## Critical Path

```
Sprint 1 (models) ──> Sprint 2 (services + sender) ──> Sprint 3 (wire + cutover) ──> Sprint 4 (PG + cleanup)
                                                              |
                                                        1 week monitoring
                                                        before Sprint 4
```

**Do NOT start Sprint 4 until Sprint 3 has run stable for at least 5 business days.** The universal sender must prove itself on SQLite before we change the database underneath it.
