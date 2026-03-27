# Paperclip Outreach

Multi-product B2B outreach system for TaggIQ, Fully Promoted Ireland, and Kritno. Django + SQLite, cron-driven email campaigns with Zoho IMAP/SMTP for reply handling. Solo founder - Prakash Inani.

## Quick Reference

- **Python**: `venv/bin/python manage.py <command>`
- **Settings**: `outreach/settings.py`
- **All models/views/admin**: `campaigns/` app

## Campaign Send Scripts

**IMPORTANT:** Do NOT use the `send_campaign` management command for sending outreach emails — it only has placeholder content. Each product has its own send scripts with proper templates:

| Product | Directory | Send Script | Templates |
|---------|-----------|------------|-----------|
| TaggIQ (BNI) | `bni-scraper/` | `send_promo_global.py`, `send_embroidery.py`, `send_email1_all.py` | In script + `email_templates.md` |
| Fully Promoted Ireland (Franchise) | `fp-ireland-master/` | `send_campaign.py` | In script + `email_templates.md` |
| FP Dublin BNI Print & Promo | `fp-ireland-master/` | `send_bni_promo.py` | In script (segment-personalised) |

Always refer to the product-specific directory for email templates, subject lines, and send logic before sending any campaign emails.

## Lead Scraping

| Source | Directory | Scripts |
|--------|-----------|---------|
| BNI Connect | `bni-scraper/` | `scrape_bni.py`, `import_promo_global.py` |
| Google Maps | `google-maps-scraper/` | `scrape_maps.py`, `import_prospects.py` |

**Google Maps Scraper** uses Google Places API (New) for business data + Playwright for email extraction from websites. Requires `GOOGLE_PLACES_API_KEY` in `.env`. See `google-maps-scraper/.env.example`.

## Sequence Filtering Rules

- **Seq 1 (Opener):** Send to `status='new'` prospects only
- **Seq 2-5 (Follow-ups):** Send to `status='contacted'` prospects only
- **Always use include-based filtering** (`status='contacted'`), never exclude-based (`exclude status__in=[...]`). Prospects with statuses like `interested`, `demo_scheduled`, `engaged` get personalized replies via `/taggiq-email-expert` or `/fp-email-expert`, not automated sequences.

## Key Commands

| Command | Purpose |
|---------|---------|
| `process_queue` | Send queued/scheduled emails |
| `check_replies` | Fetch Zoho IMAP, classify inbound, execute auto-actions |
| `review_replies` | Interactive CLI to review flagged replies |
| `seed_reply_templates` | Populate ReplyTemplate table (reference templates) |

## Website Demo Requests

When Prakash shares a new website demo request (name, company, email, phone, country, date):
1. Check if their email exists in BNI campaign DB
2. If **existing prospect**: update status to `demo_scheduled`, add phone + notes with date
3. If **new prospect**: create under Promo Global campaign, status `demo_scheduled`, `send_enabled=False`, notes tagged as "Website inquiry, not from BNI outreach"
4. **Do NOT send any email** — TaggIQ system sends the demo welcome email automatically
5. Just confirm to Prakash whether they're from BNI or new

## Email Reply Workflow

1. `check_replies` runs via cron every 5 mins (monitors all active mailboxes via MailboxConfig)
2. Opt-outs, bounces, not-interested get auto-handled (suppress, disable, cancel queue)
3. Interested, question, other get flagged with `needs_reply=True`
4. Use product-specific reply skills:
   - `/taggiq-email-expert` for TaggIQ campaign replies (Zoho SMTP)
   - `/fp-email-expert` for Fully Promoted Ireland replies (Google Workspace SMTP)
5. Review and send via `review_replies` or directly via the skill's send instructions

## Slash Commands

- `/taggiq-email-expert` — Autonomous TaggIQ email replies. Reads flagged TaggIQ inbound emails, generates replies in Prakash's voice, sends via Zoho SMTP.
- `/fp-email-expert` — Autonomous FP Ireland franchise replies. Reads flagged Fully Promoted inbound emails, generates replies focused on booking calls, sends via Google Workspace SMTP.
- `/launch-campaign` — Full GTM pipeline: scrape Google Maps → clean/dedupe → import → create send script → send. Pauses at checkpoints for approval before importing and sending.

## Skill & Agent Routing

Match the task to the right tool. Don't over-orchestrate simple tasks.

### Direct skill invocation (most tasks)

| Task type | Skill | When to use |
|-----------|-------|-------------|
| New idea, simplify a flow, brainstorm | `/innovator-engineer` | Before building something new or when something feels too complex |
| Requirements, scope, priorities | `/product-manager` | Defining what to build and why |
| System design, architecture decisions | `/cto-architect` | Before building multi-component features |
| API, database, server-side code | `/backend-engineer` | Any backend implementation work |
| UI components, frontend code | `/frontend-engineer` | Any frontend implementation work |
| AI feature design | `/ai-architect` | Deciding where/how AI fits in the product |
| AI implementation | `/ai-engineer` | Building LLM integrations, prompts, RAG |
| Tests, edge cases, QA | `/qa-automation` | After code changes, before shipping |
| Security review | `/security-auditor` | Auth changes, data handling, API exposure |
| GDPR, accessibility, compliance | `/compliance-officer` | Before launch or when handling personal data |
| UI/UX design | `/ui-designer` | Screen layouts, design system decisions |
| User research, friction analysis | `/ux-researcher` | When a flow feels wrong or users are confused |

### Multi-skill orchestration (complex features only)

Use `/chief-orchestrator` when a task clearly needs 3+ skills working in sequence. It will pick the right skills and run them in order.

Don't use it for single-skill tasks - that's overhead without value.

### Built-in agents (parallel/delegated work)

Use agents when:
- Research tasks that would bloat the conversation (Explore, general-purpose)
- Independent tasks that can run in parallel
- Scaffolding new projects (rapid-prototyper)
- Running/fixing tests after code changes (test-writer-fixer)

### Rule of thumb

1. Simple task -> invoke one skill directly
2. Multi-step feature -> chain 2-3 skills yourself (you decide order)
3. Full feature build -> /chief-orchestrator
4. Research/exploration -> Explore agent or general-purpose agent

## Products

| Product | Campaign ID | Directory |
|---------|-------------|-----------|
| TaggIQ BNI | `64ed1454-18fc-4783-9438-da18143f7312` | `bni-scraper/` |
| TaggIQ BNI Promo Global | `9cdc1870-476b-4bfe-91ff-9661bd62c662` | `bni-scraper/` |
| TaggIQ BNI Embroidery Global | `9dc977d3-f793-4051-905c-30c82b76dcd6` | `bni-scraper/` |
| FP Ireland Franchise Recruitment | `50eecf8f-c4a0-4a2d-9335-26d56870101e` | `fp-ireland-master/` |
| FP Dublin BNI Print & Promo | `3c46cbea-a817-43d5-9532-caecb2e7f01d` | `fp-ireland-master/` |

## Coding Preferences

- Python for backend/scripts, Django for web services
- Keep it simple - no abstractions until the third time you need one
- Conversational email copy - not sales copy, not corporate
- Test with real data before shipping to production
