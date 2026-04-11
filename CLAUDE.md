# Paperclip Outreach - Autonomous B2B Sales Pipeline

## Project Objective

Paperclip Outreach is a fully autonomous, multi-tenant B2B sales pipeline that takes a prospect from cold lead to booked demo with zero human intervention. It combines email outreach, AI-powered voice calling (via Vapi), intelligent reply handling (via Claude), and CRM-level prospect management into a single Django-based engine.

**The complete pipeline:**
```
Scrape leads (Google Maps / BNI Connect)
    -> Import + deduplicate into campaigns
        -> Send 5-sequence email drip (DB-driven templates, A/B tested)
            -> Monitor replies every 10 min (IMAP)
                -> Auto-classify: opt-out, bounce, interested, question
                    -> Claude AI generates personalized replies (Prakash's voice)
                    -> Auto-suppress opt-outs (product-scoped)
            -> Place AI voice calls (Vapi - segment-specific scripts)
                -> Webhook captures call outcomes, transcripts
                -> Claude analyzes transcripts -> improves call scripts
        -> Prospect status escalates: new -> contacted -> interested -> demo_scheduled
```

**Key differentiator:** This is not a tool that helps you send emails. It IS the sales team. Once configured, it runs the full outbound pipeline autonomously - scraping, emailing, calling, replying, learning, and booking demos while you sleep.

## Who This Serves

**Owner:** Prakash Inani - solo founder running three businesses through one GTM engine.

| Product | What it is | Outreach goal |
|---------|-----------|---------------|
| **TaggIQ** | POS platform for print & promo shops | Get shop owners to try the platform |
| **Fully Promoted Ireland** | Master franchise (300+ locations worldwide) | Recruit franchise partners across Ireland |
| **Kritno** | Creative production platform (future) | Not active yet |

**Future:** Design partners (e.g., Print RFT, Promotex.ie) will use the system as their own outreach engine via the multi-tenant architecture.

## Architecture (v2 - Multi-Tenant)

```
Organization ("Skillblend Ltd", future: "Print RFT")
    -> Product ("TaggIQ", "Fully Promoted Ireland", "Kritno")
        -> Campaign ("TaggIQ BNI Ireland", "FP Dublin B2B Corporate Sales")
            -> Prospect (business, contact, status, score, tier)
            -> EmailTemplate (5 sequences x A/B variants, DB-driven)
            -> EmailLog / CallLog / InboundEmail
            -> MailboxConfig (per-campaign IMAP/SMTP credentials)
        -> Suppression (product-scoped opt-outs - FP opt-out doesn't block TaggIQ)
        -> CallScript (per-segment Vapi first messages)
        -> PromptTemplate (AI prompts per product, versioned)
    -> AIUsageLog (token/cost tracking per org)
```

**Stack:** Django 4.2 + SQLite (migrating to PostgreSQL) + AWS SES + Zoho/Google IMAP + Vapi.ai + Claude CLI

**Key design principle:** Adding a new campaign = DB records only. Zero code changes. Templates, send windows, rate limits, call scripts - all configurable per campaign in the database.

---

## How The Pipeline Works

### 1. Lead Generation

```
Google Maps Scraper -> CSV with emails -> import_prospects.py -> Campaign
BNI Connect Scraper -> CSV             -> import scripts      -> Campaign
```

- Google Maps: Places API + Playwright email extraction from websites
- BNI Connect: Playwright scraper for member directories
- Always dedup before import (check existing prospects by email)

### 2. Email Sequences (Autonomous)

**Cron:** `0 11 * * 1-5` via `run_campaigns.sh` -> `python manage.py send_sequences`

The universal sender (`send_sequences`) replaces 18 legacy sender scripts:
- Reads templates from EmailTemplate model (102 templates across 11 campaigns)
- Checks send windows per campaign (timezone, hours, days)
- Applies rate limits (daily cap, min gap, batch size, inter-send delay)
- Determines A/B variant via deterministic hash
- Renders {{FNAME}}, {{COMPANY}}, {{CITY}}, {{YEAR}}, {{SEGMENT}}, {{CHAPTER}} variables
- Sends via AWS SES, logs to EmailLog, updates prospect status

**Sequence rules (include-based, never exclude):**
- Seq 1: `status='new'` AND `emails_sent=0`
- Seq 2-5: `status='contacted'` AND 7-day gap from last email
- **Never send to:** interested, engaged, demo_scheduled, design_partner (they get Claude replies only)

```bash
python manage.py send_sequences                      # All active campaigns
python manage.py send_sequences --product taggiq     # One product
python manage.py send_sequences --campaign "BNI"     # Name substring
python manage.py send_sequences --dry-run --status   # Show eligible counts
```

### 3. Reply Monitoring (Autonomous)

**Cron:** `*/10 * * * *` via `run_reply_monitor.sh`

```
IMAP check (Zoho + Google Workspace)
    -> Deduplicate by Message-ID
    -> Match to prospect (email -> In-Reply-To -> first name fallback)
    -> Classify by keywords:
        opt_out     -> disable sending, add to product-scoped suppression
        bounce      -> disable sending, suppress
        not_interested -> disable sending
        interested  -> flag for Claude reply
        question    -> flag for Claude reply
        other       -> flag for manual review
    -> Claude generates personalized reply (/taggiq-email-expert or /fp-email-expert)
    -> Reply sent via Zoho/Google SMTP with proper threading headers
    -> Prospect status updated in DB
```

**Multi-mailbox support:**
| Mailbox | Campaigns | Provider |
|---------|-----------|----------|
| `prakash@taggiq.com` | All TaggIQ campaigns | Zoho IMAP |
| `prakash@fullypromoted.ie` | FP Franchise, FP BNI | Google Workspace |
| `office@fullypromoted.ie` | FP Dublin B2B Corporate | Google Workspace |

### 4. AI Voice Calling (via Vapi)

```
place_calls command
    -> Filter eligible prospects (has phone, send_enabled, not terminal status)
    -> Look up CallScript from DB (per-segment first message)
    -> Place call via Vapi API
    -> Vapi AI handles conversation (STT -> LLM -> TTS)
    -> End-of-call webhook -> update CallLog (transcript, recording, disposition)
    -> Prospect status updated based on outcome

analyze_calls command (periodic)
    -> Claude analyzes call transcripts
    -> Generates ScriptInsight: answer_rate, interest_rate, top_objections, working_hooks
    -> Optionally pushes improved prompt to Vapi
    -> Learning loop: baseline vs post-change rate tracking
```

### 5. Prospect Lifecycle

```
new -> [Seq 1] -> contacted -> [Seq 2-5] -> ...
                                           -> interested  (Claude replies)
                                           -> engaged     (Claude replies)
                                           -> demo_scheduled
                                           -> design_partner
                                           -> not_interested (send disabled)
                                           -> opted_out     (send disabled)
```

---

## Active Campaigns

### TaggIQ (10 campaigns, ~3,600 prospects)

| Campaign | From | Prospects | Status |
|----------|------|-----------|--------|
| TaggIQ BNI Ireland | `prakash@mail.taggiq.com` | 67 | Seq 5 in progress |
| TaggIQ BNI Promo Global | `prakash@mail.taggiq.com` | 782 | Seq 3-5, largest campaign |
| TaggIQ BNI Embroidery Global | `prakash@mail.taggiq.com` | 100 | Mature |
| TaggIQ Ireland - Signs | `prakash@taggiq.com` | 102 | Seq 2 active |
| TaggIQ Ireland - Apparel | `prakash@taggiq.com` | 209 | Seq 2 active |
| TaggIQ Ireland - Print & Promo | `prakash@taggiq.com` | 586 | Seq 1-2 in progress |
| TaggIQ London - Signs | `prakash@mail.taggiq.com` | 239 | Seq 1 early |
| TaggIQ London - Apparel | `prakash@mail.taggiq.com` | 571 | Seq 1 early |
| TaggIQ London - Print & Promo | `prakash@mail.taggiq.com` | 999 | Seq 1 early |

**Positioning (TaggIQ):**
- BNI contacts: "fellow BNI member in print and promo, spent 20 years in software"
- Ireland cold leads: "spent 20 years in software before moving into this industry" - NEVER mention Fully Promoted (conflict of interest)
- Offer: 3 months free for BNI, free trial for cold leads
- Demo: `https://calendar.app.google/fzQ5iQLGHakimfjv7`
- Self-trial: `https://taggiq.com/signup`

### Fully Promoted (3 campaigns, ~430 prospects)

| Campaign | From | Prospects | Status |
|----------|------|-----------|--------|
| FP Ireland Franchise Recruitment | `prakash@fullypromoted.ie` | 194 | Seq 3-5 active |
| FP Dublin BNI Print & Promo | `prakash@fullypromoted.ie` | 235 | Seq 1 completing |
| FP Dublin B2B Corporate Sales | `office@fullypromoted.ie` | 0 | Setup (Emma voice, sending disabled) |

**Positioning (FP):** World's largest promo franchise, #1 for 25 years, 300+ locations. NOT a software pitch - business opportunity conversation.

---

## Email Infrastructure

| Route | SMTP | When to use |
|-------|------|-------------|
| Campaign outbound (sequences) | AWS SES | All sequence emails - controlled by `campaign.from_email` |
| TaggIQ replies | Zoho (`prakash@taggiq.com`) | `EmailService.send_reply()` - **always use `prakash@taggiq.com`** |
| FP Ireland replies (Prakash) | Google Workspace (`prakash@fullypromoted.ie`) | FP email expert skill |
| FP Dublin B2B replies (Emma) | Google Workspace (`office@fullypromoted.ie`) | MailboxConfig with app password |

**Critical:** BNI campaigns send FROM `prakash@mail.taggiq.com` (SES). Replies MUST use `prakash@taggiq.com` (Zoho). Using `mail.taggiq.com` for replies causes 553 relay error.

---

## Service Layer (campaigns/services/)

| Service | Purpose |
|---------|---------|
| `eligibility.py` | `get_eligible_prospects(campaign)` - include-based seq filtering + `is_suppressed(email, product)` |
| `safeguards.py` | `daily_remaining()`, `check_min_gap()`, `can_send_to_prospect()` |
| `template_resolver.py` | `get_template()` from DB, `render()` with variables, `determine_variant()` via hash |
| `send_orchestrator.py` | `send_one()` - render, send via SES, log, update prospect. Authoritative send path. |
| `ai_tracker.py` | `log_ai_call()` with cost calc, `get_prompt()` from PromptTemplate, `get_usage_summary()` |

---

## Key Commands

| Command | Purpose |
|---------|---------|
| `send_sequences` | Universal sender - replaces 18 scripts. `--product`, `--campaign`, `--dry-run`, `--status` |
| `check_replies` | Fetch IMAP mailboxes, classify, auto-handle |
| `check_replies --mailbox taggiq` | TaggIQ only |
| `check_replies --mailbox fp` | FP Ireland only (prakash@ + office@) |
| `place_calls` | Place outbound calls via Vapi for eligible prospects |
| `analyze_calls` | Claude analysis of call transcripts -> ScriptInsight |
| `process_queue` | Send queued/scheduled emails |
| `seed_templates` | Populate EmailTemplate from hardcoded scripts (one-time) |
| `review_replies` | Interactive CLI for manual reply review |

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/send/` | POST | Send a single email to a prospect |
| `/api/queue/` | POST | Queue email(s) for future sending |
| `/api/queue/status/` | GET | Queue stats per campaign |
| `/api/prospects/` | GET | List prospects with filters (campaign, product, tier, status, segment) |
| `/api/status/` | GET | Campaign sending status and safeguards |
| `/api/dashboard/` | GET | Cross-product overview (all campaigns at a glance) |
| `/api/import/` | POST | Import prospects as JSON array |
| `/api/calls/` | GET | List call logs with filters (campaign, product, status, disposition) |
| `/api/calls/stats/` | GET | Call performance metrics (answer rate, interest rate, demo rate) |
| `/api/script-insights/` | GET | AI-generated call transcript analysis |
| `/api/webhooks/vapi/` | POST | Vapi end-of-call webhook receiver |

All endpoints support `?campaign_id=` or `?product=` filtering. No auth required (local-only).

---

## Cron Schedule (fully autonomous)

**Runs inside the `outreach_cron` Docker container on Prakash's laptop.** The old macOS launchd agents (`com.paperclip.*`) are unloaded and the EC2 instance `paperclip-outreach-server` is stopped. Docker cron is the single source of truth.

Cron jobs are installed by `docker/cron-entrypoint.sh` on container start:

| Cron | Command | What it does |
|------|---------|--------------|
| `0 11 * * 1-5` | `python manage.py send_sequences` | Daily Mon-Fri 11am: universal sender |
| `*/10 * * * *` | `python manage.py handle_replies` | Every 10 min: IMAP check + Claude auto-reply for flagged emails |
| `0 9 * * 1-5` | `python manage.py post_to_social` | Daily Mon-Fri 9am: LinkedIn posts |
| `0 23 * * *` | `/app/backup_to_gdrive.sh` | Nightly: database backup to Google Drive |

### Bring the stack up / down
```bash
docker compose up -d         # start all containers
docker compose ps            # check status
docker compose logs -f cron  # tail cron container
docker compose down          # stop everything
```

### Logs (inside the cron container, not host /tmp)
- `/tmp/campaigns_daily.log` - daily send activity
- `/tmp/outreach_reply_monitor.log` - reply monitoring
- `/tmp/outreach_social.log` - LinkedIn posts
- `/tmp/outreach_backup.log` - backup activity

Access via `docker exec outreach_cron tail -f /tmp/<logfile>`.

### Laptop uptime requirement
Docker cron only runs while the Mac is awake and Docker Desktop is running. Close the lid or stop Docker and the pipeline pauses. For always-on autonomy, the path is an SDK rewrite of `handle_replies` (removes Claude Code CLI dependency) followed by redeployment to EC2.

### Why not EC2 right now
`handle_replies` subprocess-spawns the Claude Code CLI (`/Users/pinani/.local/bin/claude`) to generate personalized replies. The CLI isn't installed or authenticated on EC2, and migrating to the Anthropic Python SDK is deferred. Until that rewrite, EC2 stays parked.

---

## Skills / Slash Commands

| Skill | What it does |
|-------|-------------|
| `/chief-orchestrator` | Coordinates multi-role work across all products. Activates CTO, Backend, Sales, Email experts as needed. |
| `/taggiq-email-expert` | Reads flagged TaggIQ inbound emails, generates Prakash-voice replies, sends via Zoho |
| `/fp-email-expert` | Reads flagged FP Ireland inbound emails, generates franchise-voice replies |
| `/launch-campaign` | Full GTM pipeline: scrape -> clean -> dedup -> import -> create templates -> send |
| `/cto-architect` | Architecture decisions, code review, migration planning |
| `/ai-architect` | AI system design, model selection, token cost optimization |
| `/sales-director` | ICP definition, outbound strategy, pipeline design |
| `/email-creator` | Cold outreach copy, follow-up sequences, re-engagement campaigns |

**Before running email experts, always fetch latest replies:**
```bash
venv/bin/python manage.py check_replies --mailbox taggiq   # then /taggiq-email-expert
venv/bin/python manage.py check_replies --mailbox fp       # then /fp-email-expert
```

---

## Active Hot Leads

| Name | Company | Product | Status | Next action |
|------|---------|---------|--------|-------------|
| Paul Rivers | Print RFT, Birmingham | TaggIQ | `design_partner` | Solopress SoloFlo + Clothes2Order API integrations. Met 2026-03-31. |
| Declan Power | Promotex.ie, Wexford | TaggIQ | `design_partner` | Reseller/white-label. DecoNetwork experience. Phone: +353 872884688. |
| Sharon Bates | Keynote Marketing | TaggIQ | `interested` | Impression Europe API - chase Reece Downing (reece@impressioneurope.co.uk). |
| Linda Prudden | Linton Merch, SA | TaggIQ | `interested` | BNI Promo Global. Demo link sent 2026-03-31. |

---

## Website Demo Requests (TaggIQ)

When Prakash shares a demo request (name, company, email, phone, country, date):
1. Check if email exists in any TaggIQ campaign
2. **Existing:** `status='demo_scheduled'`, add phone + notes with date
3. **New:** create under Promo Global, `status='demo_scheduled'`, `send_enabled=False`, note "Website inquiry"
4. **Do NOT send email** - TaggIQ platform auto-sends the welcome email
5. Confirm to Prakash: existing BNI or new?

---

## Architecture Docs

| Document | Location | Purpose |
|----------|----------|---------|
| Architecture v2 Plan | `docs/architecture-v2-plan.md` | Multi-tenant design, all models, service layer, PostgreSQL migration |
| Sprint Plan | `docs/sprint-plan.md` | Implementation phases, status tracking, monitoring checklist |
| Backup & Restore | `docs/backup-and-restore.md` | Database backup and restore procedures |
| Social Studio v1 Plan | `docs/social-studio-v1-plan.md` | New `social_studio` Django app — TaggIQ LinkedIn pilot, HTML+Playwright renderer, zero-cost v1, platform-ready multi-tenant |
| Social Studio Progress | `docs/social-studio-progress.md` | Living state for social_studio implementation — read at session start, update at session end |

**v2 Status (as of 2026-04-08):**
- Sprint 1 DONE: Multi-tenant models (Organization, Product, EmailTemplate, CallScript, PromptTemplate, AIUsageLog)
- Sprint 2 DONE: Service layer + universal sender + 102 email templates seeded
- Sprint 3 DONE: Product-scoped suppressions, DB call scripts, cron cutover to send_sequences
- Sprint 4 PENDING: PostgreSQL migration (after 5-day monitoring period, earliest 2026-04-16)

---

## Backup

- **Code:** GitHub `skillblendltd/paperclip-outreach` - commit + push every session
- **Database:** `backup_to_gdrive.sh` runs nightly at 23:00
- **Not in GitHub:** `db.sqlite3`, `.env`, `venv/`

---

## Coding Rules

- Always hardcode `from_email='prakash@taggiq.com'` in `EmailService.send_reply()` - never `mail.taggiq.com`
- Sequence filtering: include-based only (`status='contacted'`), never exclude-based
- Use `campaign.product_ref` (FK) not `campaign.product` (legacy CharField) for product lookups
- Use `campaign.product_ref.slug` for the product slug string
- Suppressions are product-scoped: use `eligibility.is_suppressed(email, product)` not global check
- No hardcoded campaign IDs or templates in Python - everything in DB
- Email copy: conversational, not corporate - reads like a text from a colleague
- Never use em dashes - use hyphens with spaces instead
- Never send back-to-back correction emails - ask Prakash first
- No abstractions until the third time you need one
- Test with real data before shipping
