# Paperclip Outreach v2 - Sprint Implementation Plan

**Date:** 2026-04-08
**Last updated:** 2026-04-08
**Reference:** docs/architecture-v2-plan.md
**Approach:** 4 sprints, each ~1 session (2-4 hours). Each sprint is independently shippable.

---

## Current Status

| Sprint | Status | Reference |
|--------|--------|-----------|
| Sprint 1 | DONE | Multi-tenant models (Organization, Product, FK'd Campaigns, EmailTemplate, CallScript, PromptTemplate, AIUsageLog) |
| Sprint 2 | DONE | Service layer + universal `send_sequences` + 146 email templates seeded |
| Sprint 3 | DONE | Product-scoped suppressions, DB call scripts, cron cutover |
| Sprint 4 | DONE | Postgres 16 migration. Both local and EC2 on Docker Postgres. SQLite out of the stack entirely. |
| Sprint 5 | DONE | EC2 `paperclip-outreach-eu` (eu-west-1, `54.220.116.228`, Amazon Linux 2023 aarch64) running `outreach_cron` + `outreach_web` + `outreach_db`. Claude Code CLI baked into image. Cron partition: `--product print-promo` (Lisa). |
| Sprint 5 v5 | DONE | Org-agnostic AI reply pipeline. Voice in `PromptTemplate`, mechanics in code. See `docs/ai-reply-architecture.md`. |
| Sprint 6 Phase 1A | DONE (paused) | TaggIQ Warm Re-engagement campaign seeded, 15 prospects, `sending_enabled=False`. Blocked on Loom URL. See `docs/sprint-6-state.md`. |
| Sprint 6 Phase 2A | DONE | Greenfield services (`conversation`, `context_assembler`, `channel_timing`, `ai_budget`, `cacheable_preamble`) shipped as dark code. 38/38 tests pass. |
| Sprint 6 Phase 2B | FOLDED INTO SPRINT 7 | Wiring Phase 2A services into live code is Phase 7.2 of the Sprint 7 plan. |
| **Sprint 7** | **PLANNED** | **Sales Director Platform MVP.** Per-product `ProductBrain` + per-campaign overrides, rules engine, `next_action` service, golden-set eval, two-host rollout. See `docs/sprint-7-implementation-plan.md` and `docs/sprint-7-progress.md`. |

**Two-host production architecture (as of Sprint 5):**
- Local Docker (Prakash's laptop) — TaggIQ (all), FP Ireland Franchise Recruitment, FP Dublin BNI Print & Promo. Cron: `--exclude-product print-promo`.
- EC2 `paperclip-outreach-eu` — FP Kingswood Business Area, Dublin Construction & Trades (Lisa v5 print-promo voice). Cron: `--product print-promo`. Always-on.

Both hosts run Postgres 16 on the same schema (`0016_sprint6_loom_hook_flag_budget`). Migrations apply to both, brain rows are seeded per host.

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

## Sprint 5: EC2 Deployment - DONE

See `docs/ec2-deployment-runbook.md` for the original plan. Actual outcome:

- `paperclip-outreach-eu` live in eu-west-1 (`54.220.116.228`), Amazon Linux 2023 aarch64
- Node 20 + Claude Code CLI baked into `outreach_cron` Docker image
- OAuth token persists in `claude_auth` named volume
- Cron partitioned via `CRON_SEND_ARGS` / `CRON_REPLY_ARGS` env vars:
  - Local: `--exclude-product print-promo`
  - EC2:   `--product print-promo`
- Zero split-brain risk — each campaign runs on exactly one host
- Always-on for Lisa's print-promo reply pipeline; laptop can sleep without pausing Lisa

---

## Sprint 6: Contextual Autonomous Marketing - Phase 1A + 2A DONE, rest folded into Sprint 7

See `docs/contextual-autonomous-marketing.md` (vision) and `docs/sprint-6-state.md` (execution).

**Completed:**
- Phase 1A — TaggIQ Warm Re-engagement campaign seeded: 15 prospects, 4 sequence emails, 1 Vapi call target, `sending_enabled=False` pending Loom URL from Prakash
- Phase 2A — Greenfield services (`conversation.py`, `context_assembler.py`, `channel_timing.py`, `ai_budget.py`, `cacheable_preamble.py`) shipped as dark code. 38/38 tests pass. Zero impact on live path.
- `Campaign.use_context_assembler` flag added in migration `0016`, defaults `False`

**Deferred into Sprint 7:**
- Phase 2B (wire services into live code) → becomes Phase 7.2
- Phase 2C (generalize beyond TaggIQ) → becomes Phase 7.4 EC2 rollout
- The brain/rules-engine layer that was implicit in Phase 2 becomes explicit in Sprint 7

Note: The Sprint 6 plan called for a TaggIQ webhook bridge (trial lifecycle campaigns). That work is deferred to a future sprint — it's orthogonal to the contextual marketing + brain platform direction taken in Sprint 6/7.

---

## Sprint 7: Sales Director Platform MVP - PLANNED

**Prerequisite:** Prakash approval to start Phase 7.0 (golden set capture, ~90 min)
**Full plan:** `docs/sprint-7-implementation-plan.md`
**Live state:** `docs/sprint-7-progress.md`

Summary:
- Each Product (and optionally each Campaign) gets its own "brain" — JSON rules + voice `PromptTemplate` row. Platform everything else.
- New models: `ProductBrain` (1:1 Product), `CampaignBrainOverride` (sparse 1:1 Campaign). One additive column `AIUsageLog.brain_version`. Migration `0017`.
- New services: `brain.py`, `rules_engine.py`, `next_action.py`, `eval_harness.py`, `vapi_opener.py`. Pure-Python rules engine, zero LLM on decisioning.
- Wires Sprint 6 Phase 2A services into live code behind `Campaign.use_context_assembler` flag
- Golden set eval harness (Opus 4.6 as judge) gates every merge touching reply/LLM paths
- Sonnet 4.6 floor on all content-generation jobs, configurable per-brain via `jobs` JSON
- Two brains running in production simultaneously (TaggIQ + FP Franchise on local, FP print-promo on EC2) is the MVP acceptance test
- Zero impact on existing campaigns — flag=False path is byte-sacred during build

**Phases:**
1. 7.0 — Eval foundation (2 days, HARD BLOCKER)
2. 7.1 — Data model + brain authoring (3 days, local)
3. 7.2 — Wire executors through brain (5 days, local, feature-flagged)
4. 7.3 — Local rollout (3 days, TaggIQ Warm Re-engagement first)
5. 7.4 — EC2 rollout (2 days, Lisa print-promo)
6. 7.5 — Cleanup + documentation

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
