# Paperclip Outreach — GTM & Campaign Engine

**What this is:** A fully autonomous B2B outreach system for three products.
Scrapes leads → imports to campaigns → sends multi-sequence emails → monitors replies → auto-replies via Claude AI → updates CRM status. **Zero human intervention required for day-to-day operation.**

**Owner:** Prakash Inani — solo founder running TaggIQ (software), Fully Promoted Ireland (franchise), and Kritno.
**Stack:** Django + SQLite + AWS SES + Zoho IMAP + Claude CLI

## Cron Schedule (fully autonomous)

| Cron | Script | What it does |
|------|--------|--------------|
| `0 11 * * 1-5` | `run_campaigns.sh` | Daily Mon–Fri 11am IST: sends all due sequences across all campaigns |
| `*/10 * * * *` | `run_reply_monitor.sh` | Every 10 min: checks Zoho IMAP, auto-handles opt-outs/bounces, invokes `claude -p "/taggiq-email-expert"` for flagged replies |
| `0 23 * * *` | `backup_to_gdrive.sh` | Nightly: backs up db.sqlite3 to Google Drive |

### Daily send pipeline (`run_campaigns.sh`):
1. `bni-scraper/send_sequence.py` — BNI Ireland + Promo Global + Embroidery Global (seq 1–5)
2. `google-maps-scraper/send_ireland_sequences.py` — Ireland Signs + Apparel + Print & Promo (seq 1–5)

### Logs:
- `/tmp/campaigns_daily.log` — daily send activity
- `/tmp/taggiq_reply_monitor.log` — reply monitoring
- `/tmp/taggiq_claude_replies.log` — Claude reply output

---

## The Three Products & Their Campaigns

### 1. TaggIQ — `product='taggiq'`
Next-gen POS platform for print & promo shops. Quotes, artwork approvals, orders, invoicing in one place. Prakash built it from his own frustration running Fully Promoted Dublin.

**Positioning:**
- To BNI contacts: "fellow BNI member in print and promo, spent 20 years in software"
- To Ireland cold leads: "spent 20 years in software before moving into this industry" — NEVER mention Fully Promoted (conflict of interest with Irish shops)
- Offer: 3 months free for BNI members, free trial for cold leads
- Demo link: `https://calendar.app.google/fzQ5iQLGHakimfjv7`
- Self-trial: `https://taggiq.com/signup`

**Reply handler: `/taggiq-email-expert`**

| Campaign | ID | From | Prospects | Seqs Sent | Status |
|----------|----|------|-----------|-----------|--------|
| TaggIQ BNI Ireland | `64ed1454-18fc-4783-9438-da18143f7312` | `prakash@mail.taggiq.com` | 67 | 1–5 (seq 5 in progress) | Active |
| TaggIQ BNI Promo Global | `9cdc1870-476b-4bfe-91ff-9661bd62c662` | `prakash@mail.taggiq.com` | 781 | 1–3 done, seq 4 pending | Active |
| TaggIQ BNI Embroidery Global | `9dc977d3-f793-4051-905c-30c82b76dcd6` | `prakash@mail.taggiq.com` | 100 | 1–5 (seq 5 in progress) | Active |
| TaggIQ Ireland — Signs | `74de42a1-5bab-4e31-ada8-c200b18f1403` | `prakash@taggiq.com` | 102 | Seq 1 done (100 sent) | Seq 2 from 2026-04-06 |
| TaggIQ Ireland — Apparel | `7a44100a-d848-4619-b239-d8502c74e052` | `prakash@taggiq.com` | 209 | Seq 1: 100 sent, 109 new remaining | Seq 2 from 2026-04-06 |
| TaggIQ Ireland — Print & Promo | `0ad82b87-c55e-4458-a426-cef6baf0d088` | `prakash@taggiq.com` | 586 | Seq 1: 99 sent, 487 new remaining | Seq 2 from 2026-04-06 |

### 2. Fully Promoted Ireland — `product='fullypromoted'`
Franchise recruitment campaign. Prakash is Master Franchisee for Ireland. Re-engaging ~191 old leads (2016–2025) who enquired about opening a store. Goal: book a discovery call.

**Positioning:** World's largest promo franchise, #1 for 25 years, 300+ locations, Ireland now open. NOT a software pitch — this is a business opportunity conversation.

**Reply handler: `/fp-email-expert`**

| Campaign | ID | From | Prospects | Seqs Sent | Status |
|----------|----|------|-----------|-----------|--------|
| FP Ireland Franchise Recruitment | `50eecf8f-c4a0-4a2d-9335-26d56870101e` | `prakash@fullypromoted.ie` | 193 | Seq 1 + 2 done | Active |
| FP Dublin BNI Print & Promo | `3c46cbea-a817-43d5-9532-caecb2e7f01d` | `prakash@fullypromoted.ie` | 235 | Seq 1: 76 sent | Active |

### 3. Kritno — `product='kritno'`
Creative production platform — artwork, proofing, design workflow. Different buyer (designers, agencies, print-heavy businesses). No campaigns active yet. No mailbox set up.

---

## Autonomous Reply System

**The cron runs every 10 minutes. It is fully autonomous.**

```
*/10 * * * * /Users/pinani/Documents/paperclip-outreach/run_reply_monitor.sh
0 23 * * * /Users/pinani/Documents/paperclip-outreach/backup_to_gdrive.sh
```

### Flow for TaggIQ replies:
```
Zoho IMAP → check_replies → classify → auto-handle opt-outs/bounces
                                     → flag interested/questions
                                     → claude -p "/taggiq-email-expert"
                                     → reply sent + prospect status updated in DB
```

### Flow for FP Ireland replies:
```
Zoho IMAP (fp mailbox) → check_replies --mailbox fp → classify
                       → flag interested/questions
                       → invoke /fp-email-expert manually or via cron
```

### What check_replies auto-handles (no Claude needed):
| Classification | Action |
|---------------|--------|
| `opt_out` | `send_enabled=False`, queued emails cancelled |
| `bounce` | `send_enabled=False` |
| `not_interested` | `send_enabled=False` |
| `auto_reply` | Mark seen, no action |

### What Claude handles (via `/taggiq-email-expert` or `/fp-email-expert`):
Replies classified as `interested`, `question`, `other` — generates personalised reply, sends, updates prospect `status` and `notes` in DB.

### After Claude replies, prospect status is set to:
| Reply type | Status |
|-----------|--------|
| Asking about features, pricing, demo | `interested` |
| Booked or confirmed demo | `demo_scheduled` |
| Active back-and-forth | `engaged` |
| Reseller / channel partner interest | `design_partner` |
| Polite no / too busy | `not_interested` |
| No clear signal | unchanged |

### Logs:
- `/tmp/taggiq_reply_monitor.log` — cron activity
- `/tmp/taggiq_claude_replies.log` — Claude reply output

### Domain mismatch fix (added 2026-03-31):
If someone replies from a different email than what's in DB (e.g. `@lintonmerch.co.za` vs `@lintonent.co.za`), `check_replies` now auto-matches via:
1. **In-Reply-To** → matches SES message ID in EmailLog (primary)
2. **First-name** → matches decision_maker_name if unique (fallback)

---

## Email Infrastructure

| Route | SMTP | When to use |
|-------|------|-------------|
| Campaign outbound | AWS SES | All sequence emails — controlled by `campaign.from_email` |
| TaggIQ replies | Zoho (`prakash@taggiq.com`) | `EmailService.send_reply()` — **always hardcode `from_email='prakash@taggiq.com'`** |
| FP Ireland replies | Google Workspace (`prakash@fullypromoted.ie`) | FP email expert skill handles this |

**Critical:** BNI campaigns send FROM `prakash@mail.taggiq.com` (SES). But reply-back MUST use `prakash@taggiq.com` (Zoho). If you use `mail.taggiq.com` for replies, Zoho throws 553 relay error.

---

## Prospect Status Lifecycle

```
new → [Seq 1 sent] → contacted → [Seq 2–5 sent] → ...
                                                  → interested  (Claude replies)
                                                  → engaged     (Claude replies)
                                                  → demo_scheduled
                                                  → design_partner
                                                  → not_interested (send disabled)
                                                  → opted_out     (send disabled)
```

**Sequence filtering rules — always use include-based:**
- Seq 1: `status='new'` AND `emails_sent=0`
- Seq 2–5: `status='contacted'` AND 7-day gap from last email
- **Never send sequences to `interested`, `engaged`, `demo_scheduled`, `design_partner`** — they get Claude replies only

---

## Send Scripts Map

**All campaigns run automatically via `run_campaigns.sh` at 11am Mon–Fri. No manual action needed.**
Do NOT use `send_campaign` management command (placeholder only).

### Automated (via run_campaigns.sh cron)
| Script | Campaigns covered | Seqs |
|--------|-------------------|------|
| `bni-scraper/send_sequence.py` | BNI Ireland, Promo Global, Embroidery Global | 1–5 |
| `google-maps-scraper/send_ireland_sequences.py` | Ireland Signs, Apparel, Print & Promo | 1–5 |

### Manual one-off scripts (use if cron missed or for testing)
| Script | Campaign | Seq |
|--------|----------|-----|
| `bni-scraper/send_sequence.py --campaign bni` | BNI Ireland only | 1–5 |
| `bni-scraper/send_sequence.py --campaign promo` | Promo Global only | 1–5 |
| `bni-scraper/send_sequence.py --campaign embroidery` | Embroidery only | 1–5 |
| `google-maps-scraper/send_ireland_sequences.py --campaign signs` | Ireland Signs | 1–5 |
| `google-maps-scraper/send_ireland_sequences.py --campaign apparel` | Ireland Apparel | 1–5 |
| `google-maps-scraper/send_ireland_sequences.py --campaign print` | Ireland Print & Promo | 1–5 |

### Fully Promoted (fp-ireland-master/) — manual only
| Script | Campaign | Seq |
|--------|----------|-----|
| `send_campaign.py` | FP Franchise Recruitment | 1–5 |
| `send_bni_promo.py` | FP Dublin BNI | 1 |

---

## Lead Scraping Pipeline

```
Google Maps Scraper → CSV with emails → import_prospects.py → Campaign → Send Scripts
BNI Connect Scraper → CSV          → import_promo_global.py → Campaign → Send Scripts
```

### Google Maps Scraper (google-maps-scraper/)
- Uses Google Places API (New) + Playwright for email extraction from websites
- `GOOGLE_PLACES_API_KEY` required in `.env`
- Run: `PYTHONPATH=. ../venv/bin/python scrape_maps.py --config <config> --output <name>`
- Configs: `config.py` (Ireland), `config_london.py`, `config_london_boroughs.py`, `config_uk.py`
- After scraping: run `import_prospects.py --campaign-id <uuid> --csv output/<file>.csv`

### UK / London scrape status (as of 2026-03-31):
- `uk_london_20260329.csv` — 926 businesses, 12 emails (Central London)
- `uk_london_boroughs_20260330.csv` — 3,054 businesses (33 boroughs × 10 keywords), email extraction running via `extract_emails_borough.py` — saves every 50 records
- **Next:** merge both London files, dedupe, import to new London TaggIQ campaigns

### Dedup before import — always check:
```bash
venv/bin/python manage.py shell -c "
from campaigns.models import Prospect
import csv
with open('google-maps-scraper/output/<FILE>.csv') as f:
    rows = list(csv.DictReader(f))
scraped = {r['email'].lower() for r in rows if r.get('email')}
existing = {e.lower() for e in Prospect.objects.filter(email__in=scraped).values_list('email', flat=True)}
print(f'New: {len(scraped - existing)} | Dupes: {len(scraped & existing)}')
"
```

---

## Skills / Slash Commands

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `/taggiq-email-expert` | Manual or via cron | Reads all flagged TaggIQ inbound emails, generates Prakash-voice replies, sends via Zoho SMTP, updates prospect status + notes |
| `/fp-email-expert` | Manual | Reads flagged FP Ireland inbound emails, generates franchise-voice replies, goal is to book a discovery call |
| `/launch-campaign` | Manual | Full GTM pipeline: scrape → clean → dedup → import → create send script → send (checkpoints before import and send) |
| `/cto-architect` | Manual | Architecture decisions for the outreach system |
| `/gtm-strategist` | Manual | Market entry strategy, ICP, channel planning |

**When invoked manually, always run check_replies first to get latest inbound:**
```bash
venv/bin/python manage.py check_replies --mailbox taggiq
# then /taggiq-email-expert

venv/bin/python manage.py check_replies --mailbox fp
# then /fp-email-expert
```

---

## Key Commands

| Command | Purpose |
|---------|---------|
| `check_replies` | Fetch all mailboxes, classify, auto-handle |
| `check_replies --mailbox taggiq` | TaggIQ only |
| `check_replies --mailbox fp` | FP Ireland only |
| `process_queue` | Send queued/scheduled emails |
| `review_replies` | Interactive CLI for manual reply review |
| `seed_reply_templates` | Populate ReplyTemplate table |

---

## Active Hot Leads (update as status changes)

| Name | Company | Email | Product | Status | Next action |
|------|---------|-------|---------|--------|-------------|
| Paul Rivers | Print RFT, Birmingham | hello@printrft.co.uk | TaggIQ | `design_partner` | Solopress SoloFlo + Clothes2Order API integrations in progress. Met 2026-03-31. |
| Declan Power | Promotex.ie, Wexford | — | TaggIQ | `design_partner` | Reseller/white-label. DecoNetwork experience. Phone: +353 872884688. |
| Sharon Bates | Keynote Marketing | — | TaggIQ | `interested` | Impression Europe API — chase Reece Downing (reece@impressioneurope.co.uk). |
| Linda Prudden | Linton Merch, SA | linda@lintonmerch.co.za | TaggIQ | `interested` | BNI Promo Global. Demo link sent 2026-03-31. Also in DB as Linda@lintonent.co.za. |

---

## Website Demo Requests (TaggIQ)

When Prakash shares a demo request (name, company, email, phone, country, date):
1. Check if email exists in any TaggIQ campaign
2. **Existing:** `status='demo_scheduled'`, add phone + notes with date
3. **New:** create under Promo Global, `status='demo_scheduled'`, `send_enabled=False`, note "Website inquiry"
4. **Do NOT send email** — TaggIQ platform auto-sends the welcome email
5. Confirm to Prakash: existing BNI or new?

---

## Backup

- **Code:** GitHub `skillblendltd/paperclip-outreach` — commit + push every session
- **Database:** `backup_to_gdrive.sh` runs nightly at 23:00 — backs up `db.sqlite3` to Google Drive
- **Not in GitHub:** `db.sqlite3`, `.env`, `venv/`
- See `docs/backup-and-restore.md` for restore procedure

---

## Coding Rules

- Always hardcode `from_email='prakash@taggiq.com'` in `EmailService.send_reply()` — never `mail.taggiq.com`
- Sequence filtering: include-based only (`status='contacted'`), never exclude-based
- No abstractions until the third time you need one
- Test with real data before shipping
- Email copy: conversational, not corporate — reads like a text from a colleague
