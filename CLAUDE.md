# Paperclip Outreach — Full Operational Context

Multi-product B2B outreach system for TaggIQ, Fully Promoted Ireland, and Kritno.
Django + SQLite, cron-driven email campaigns with Zoho IMAP/SMTP for reply handling.
Solo founder: **Prakash Inani** (prakash@taggiq.com / prakash@fullypromoted.ie)

---

## Infrastructure

- **Python**: `venv/bin/python manage.py <command>`
- **Settings**: `outreach/settings.py`
- **All models/views/admin**: `campaigns/` app
- **Database**: SQLite at `db.sqlite3` — backed up nightly to Google Drive
- **Outbound email**: AWS SES (supports any verified domain)
- **Reply handling**: Zoho IMAP (`imappro.zoho.eu:993`) for prakash@taggiq.com
- **FP replies**: Google Workspace SMTP for prakash@fullypromoted.ie

### Critical Email Sending Rules
- Campaign outbound uses SES — `campaign.from_email` controls the From header
- **BNI campaigns** send from `prakash@mail.taggiq.com` (SES verified)
- **Reply emails** (`EmailService.send_reply`) MUST always use `from_email='prakash@taggiq.com'` — Zoho SMTP only authorises this address. Never use `mail.taggiq.com` for replies or it will 553 relay error.
- Ireland cold campaigns send from `prakash@taggiq.com`

---

## Products & Campaigns

| Product | Campaign Name | Campaign ID | Directory | From Email |
|---------|--------------|-------------|-----------|------------|
| TaggIQ BNI Ireland | TaggIQ BNI | `64ed1454-18fc-4783-9438-da18143f7312` | `bni-scraper/` | `prakash@mail.taggiq.com` |
| TaggIQ BNI Promo Global | TaggIQ BNI Promo Global | `9cdc1870-476b-4bfe-91ff-9661bd62c662` | `bni-scraper/` | `prakash@mail.taggiq.com` |
| TaggIQ BNI Embroidery Global | TaggIQ BNI Embroidery Global | `9dc977d3-f793-4051-905c-30c82b76dcd6` | `bni-scraper/` | `prakash@mail.taggiq.com` |
| TaggIQ Ireland — Signs | TaggIQ Ireland — Signs & Signage | (check DB) | `google-maps-scraper/` | `prakash@taggiq.com` |
| TaggIQ Ireland — Apparel | TaggIQ Ireland — Apparel & Embroidery | (check DB) | `google-maps-scraper/` | `prakash@taggiq.com` |
| TaggIQ Ireland — Print & Promo | TaggIQ Ireland — Print & Promo | (check DB) | `google-maps-scraper/` | `prakash@taggiq.com` |
| FP Ireland Franchise | FP Ireland Franchise Recruitment | `50eecf8f-c4a0-4a2d-9335-26d56870101e` | `fp-ireland-master/` | `prakash@fullypromoted.ie` |
| FP Dublin BNI | FP Dublin BNI Print & Promo | `3c46cbea-a817-43d5-9532-caecb2e7f01d` | `fp-ireland-master/` | `prakash@fullypromoted.ie` |

---

## Autonomous Reply System (CRITICAL)

**The cron job runs every 10 minutes and is fully autonomous.**

```
*/10 * * * * /Users/pinani/Documents/paperclip-outreach/run_reply_monitor.sh
```

### What runs automatically:
1. `check_replies --mailbox taggiq` — fetches Zoho IMAP, classifies inbound emails
2. Auto-handles: `opt_out` (suppresses prospect), `bounce` (disables send), `not_interested` (disables send)
3. If any emails flagged `needs_reply=True` → invokes `claude -p "/taggiq-email-expert"` via CLI
4. Claude reads emails, generates replies in Prakash's voice, sends via Zoho SMTP, updates prospect status + notes in DB
5. macOS notification on completion

### Logs:
- `/tmp/taggiq_reply_monitor.log` — cron activity
- `/tmp/taggiq_claude_replies.log` — Claude's full reply output

### Manual invocation:
```bash
cd /Users/pinani/Documents/paperclip-outreach
venv/bin/python manage.py check_replies --mailbox taggiq
# Then invoke /taggiq-email-expert
```

### Domain mismatch handling (fixed 2026-03-31):
Some prospects reply from a different email than what's in the DB (e.g. `@lintonmerch.co.za` vs `@lintonent.co.za`). `check_replies` now resolves this via:
1. **In-Reply-To matching** — matches SES message ID in EmailLog (most reliable)
2. **First-name matching** — matches decision_maker_name (only if unique result)

If a NO MATCH slips through, manually link:
```python
ie = InboundEmail.objects.get(id='<id>')
ie.prospect = Prospect.objects.get(id='<prospect_id>')
ie.campaign = ie.prospect.campaign
ie.save(update_fields=['prospect', 'campaign', 'updated_at'])
```

---

## Prospect Status Lifecycle

| Status | Meaning | Auto-sequences? |
|--------|---------|----------------|
| `new` | Never emailed | Seq 1 only |
| `contacted` | Received 1+ emails, no reply | Seq 2–5 |
| `interested` | Replied positively, asking questions | No — Claude replies |
| `engaged` | Active back-and-forth | No — Claude replies |
| `demo_scheduled` | Booked a demo call | No |
| `design_partner` | Agreed to be design partner / reseller | No |
| `not_interested` | Declined, send disabled | No |
| `opted_out` | Unsubscribed, send disabled | No |

**Always use include-based filtering** (`status='contacted'`), never exclude-based. Prospects above `contacted` get Claude replies only — never sequence emails.

---

## Sequence Rules

- **Seq 1**: `status='new'`, `emails_sent=0`
- **Seq 2+**: `status='contacted'`, minimum 7-day gap from last email
- **Batch size**: 100/day for all campaigns
- **Delay**: 60s between sends (BNI), 30–60s random (Promo Global)
- **Never skip sequences** — always check emails_sent count before running

### Send Scripts

| Campaign | Seq 1 | Seq 2+ |
|----------|-------|--------|
| BNI Ireland | `bni-scraper/send_email1_all.py` | `bni-scraper/send_sequence.py` |
| Promo Global | `bni-scraper/send_promo_global.py` | `bni-scraper/send_seq2_promo_global.py`, `send_seq3_all.py`, `send_sequence.py` |
| Embroidery Global | `bni-scraper/send_embroidery.py` | `bni-scraper/send_sequence.py` |
| Ireland Signs | `google-maps-scraper/send_ireland_signs_seq1.py` | **Seq 2 not yet created — needed 2026-04-06** |
| Ireland Apparel | `google-maps-scraper/send_ireland_apparel_seq1.py` | **Seq 2 not yet created — needed 2026-04-06** |
| Ireland Print & Promo | `google-maps-scraper/send_ireland_print_promo_seq1.py` | **Seq 2 not yet created — needed 2026-04-06** |

---

## Campaign Send Scripts

**Do NOT use the `send_campaign` management command** — it has only placeholder content.

All email templates live inside the send scripts themselves. Check the script for subject lines, body HTML, and A/B variants before running.

---

## Lead Scraping

| Source | Directory | Scripts |
|--------|-----------|---------|
| BNI Connect | `bni-scraper/` | `scrape_bni.py`, `import_promo_global.py` |
| Google Maps | `google-maps-scraper/` | `scrape_maps.py`, `import_prospects.py` |

**Google Maps Scraper** uses Google Places API (New) + Playwright for email extraction.
Requires `GOOGLE_PLACES_API_KEY` in `.env`. See `google-maps-scraper/.env.example`.

### London scrape status (as of 2026-03-31):
- `uk_london_20260329.csv` — 926 businesses, 12 emails (Central London)
- `uk_london_boroughs_20260330.csv` — 3,054 businesses, email extraction running via `extract_emails_borough.py` (saves every 50 records to CSV+JSON)
- Next step: merge + dedupe both files, import to London TaggIQ campaigns

---

## Key Commands

| Command | Purpose |
|---------|---------|
| `process_queue` | Send queued/scheduled emails |
| `check_replies` | Fetch all mailboxes, classify inbound, auto-handle |
| `check_replies --mailbox taggiq` | TaggIQ mailbox only |
| `check_replies --mailbox fp` | FP Ireland mailbox only |
| `review_replies` | Interactive CLI to review flagged replies |
| `seed_reply_templates` | Populate ReplyTemplate table |

---

## Slash Commands / Skills

| Skill | Purpose |
|-------|---------|
| `/taggiq-email-expert` | Autonomous TaggIQ replies — reads flagged inbound, replies in Prakash's voice via Zoho SMTP, updates prospect status + notes in DB |
| `/fp-email-expert` | Autonomous FP Ireland franchise replies |
| `/launch-campaign` | Full GTM pipeline: scrape → clean/dedupe → import → send |
| `/cto-architect` | System design and architecture |
| `/gtm-strategist` | Go-to-market planning |
| `/backend-engineer` | Backend code implementation |

---

## Website Demo Requests

When Prakash shares a new demo request (name, company, email, phone, country, date):
1. Check if email exists in BNI campaign DB
2. **Existing prospect**: update `status='demo_scheduled'`, add phone + notes with date
3. **New prospect**: create under Promo Global campaign, `status='demo_scheduled'`, `send_enabled=False`, notes: "Website inquiry"
4. **Do NOT send any email** — TaggIQ system sends the welcome email automatically
5. Confirm to Prakash: existing BNI or new?

---

## Active Hot Leads

Keep this updated as statuses change.

| Name | Company | Email | Status | Notes |
|------|---------|-------|--------|-------|
| Paul Rivers | Print RFT, Birmingham | hello@printrft.co.uk | `design_partner` | Solopress SoloFlo API + Clothes2Order integrations in progress. Met 2026-03-31. |
| Declan Power | Promotex.ie, Wexford | — | `design_partner` | Reseller/channel partner. DecoNetwork experience. Phone: +353 872884688. |
| Sharon Bates | Keynote Marketing | — | `interested` | Impression Europe API — awaiting credentials from Reece Downing (reece@impressioneurope.co.uk). |
| Linda Prudden | Linton Merch, SA | linda@lintonmerch.co.za | `interested` | BNI Promo Global. Also stored as Linda@lintonent.co.za. Demo link sent 2026-03-31. |

---

## Backup Strategy

- **Code**: GitHub (`skillblendltd/paperclip-outreach`) — commit + push after every session
- **Database**: `backup_to_gdrive.sh` runs at 23:00 daily (cron). Backs up `db.sqlite3` to Google Drive.
- **Not in GitHub**: `db.sqlite3`, `.env`, `venv/`

---

## Coding Preferences

- Python + Django — no over-engineering
- No abstractions until the third time you need one
- Conversational email copy — not sales copy
- Test with real data before shipping
- Always hardcode `from_email='prakash@taggiq.com'` in `EmailService.send_reply()` calls
