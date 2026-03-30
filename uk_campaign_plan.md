# TaggIQ UK Campaign Plan
# Created: 2026-03-29
# Owner: Prakash Inani

## Overview

Phased UK market entry for TaggIQ targeting print shops, promotional product
distributors, embroidery/apparel shops, sign shops, and decoration businesses.

UK is ~13x Ireland. Estimated 10,000-15,000 target businesses total.
Approach: one city at a time, rolling pipeline — always one city sending,
one city being scraped, one city being imported.

---

## Products in Scope

| Product | Email | Status |
|---------|-------|--------|
| TaggIQ UK | prakash@taggiq.com | Active — launching London first |
| Fully Promoted UK Franchise | prakash@fullypromoted.ie | HOLD — check FP corporate for open UK territories |
| Kritno UK | TBD (no mailbox yet) | HOLD — 6-8 weeks out |

---

## Campaign Structure

4 UK campaigns (segment-based, NOT city-based).
All cities import into the same campaigns — London first, then Manchester, etc.

| Campaign Name | Segments | Pain Angle |
|---------------|----------|------------|
| TaggIQ UK — Print & Promo | promo_distributor + print_shop | Artwork approvals over email/WhatsApp |
| TaggIQ UK — Apparel & Embroidery | apparel_embroidery | Decoration specs lost in emails, job tracking |
| TaggIQ UK — Signs & Signage | signs | Design approvals before production, costly mistakes |
| TaggIQ UK — Mixed | anything unclassified | Generic print/workflow angle |

---

## City Prioritisation

| Phase | Cities | Est. Businesses | Start When |
|-------|--------|-----------------|------------|
| Phase 1 | London (all 5 areas) | 1,500-2,000 | NOW |
| Phase 2 | Manchester + Birmingham | 600-900 | When London is 50% sent |
| Phase 3 | Glasgow + Edinburgh | 400-600 | When Phase 2 is 50% sent |
| Phase 4 | Leeds + Liverpool + Bristol | 600-900 | Rolling |
| Phase 5 | Sheffield + Nottingham + Leicester + Cardiff | 400-600 | Rolling |
| Phase 6 | All remaining regional cities | 3,000-5,000 | Rolling |

---

## London Scrape Plan

### London Areas (5 total)
- Central London — DONE (291 rows)
- North London — DONE (353 rows)
- South London — PARTIAL (40 rows, needs completion)
- East London — TODO
- West London — TODO

### Keywords per area
Core (all areas):       promotional products, embroidery shop, print shop, sign shop,
                        custom apparel, screen printing, uniform supplier, signage company

Extended (all areas):   branded merchandise, corporate gifts, workwear supplier,
                        banner printing, DTF printing, garment decoration,
                        heat transfer printing, sublimation printing

### Output files
- Maps data: google-maps-scraper/output/uk_london_20260329.csv
- Email extraction: run separately after maps scrape completes

### Scrape command
```
cd /Users/pinani/Documents/paperclip-outreach/google-maps-scraper
PYTHONPATH=. ../venv/bin/python scrape_maps.py --config config_london \
  --output uk_london_20260329 --resume
```

---

## Send Strategy

### Volume limits
- Max 100 emails/day per campaign
- 60-second delay between sends (existing infrastructure)
- All TaggIQ UK campaigns share prakash@taggiq.com — stagger launches

### Stagger schedule (to avoid reply wall)
| Week | New campaign launching |
|------|----------------------|
| W1 | Ireland campaigns only (get stable first) |
| W3 | TaggIQ UK — Print & Promo (London) |
| W5 | TaggIQ UK — Apparel & Embroidery (London) |
| W6 | TaggIQ UK — Signs & Signage (London) |
| W7+ | All campaigns + Manchester import |

### Send windows
- Mon-Fri only, 9am-5pm UK time (UTC+1 from 30 March 2026 / BST)
- Priority order within each batch: highest-rated businesses first

---

## Email Templates — UK Versions

### Trust signal (replaces BNI / Ireland references)
"I spent 20 years in software before moving into the print and promo industry"
Geography: "shops I've spoken with across the UK and Ireland"
No mention of Dublin or Ireland in cold openers.

### Sequence cadence
Same as Ireland: Day 0, 5, 14, 26, 40

### Templates by segment

#### Print & Promo
Email 1 — Conversation Starter
  Subject A: quick question about {{COMPANY}}
  Subject B: a question for the team at {{COMPANY}}
  Body: artwork approvals over email/WhatsApp angle

Email 2 — Shared Pain
  Subject A: the artwork approval problem
  Subject B: thought you'd find this useful
  Body: introduce TaggIQ, keep it soft

Email 3 — Builder Story
  Subject A: why I built TaggIQ
  Subject B: a different approach to running a promo shop
  Body: 20yr software background, free trial offer, demo link

Email 4 — Real Pain
  Subject A: artwork approvals over email = nightmare
  Subject B: one thing most promo shops get wrong
  Body: direct, close with demo offer

Email 5 — Breakup
  Subject: last one from me, {{FNAME}}
  Body: short close, leave door open

#### Apparel & Embroidery
Pain angle: decoration specs lost in emails, wrong thread colour = redo the job
Same 5-email structure, segment-specific copy

#### Signs & Signage
Pain angle: design approvals before production, vehicle wraps expensive to redo
Same 5-email structure, segment-specific copy

---

## Send Scripts to Create

| Script | Campaign | Notes |
|--------|----------|-------|
| send_uk_print_promo_seq1.py | TaggIQ UK — Print & Promo | Segments: promo_distributor + print_shop |
| send_uk_apparel_seq1.py | TaggIQ UK — Apparel & Embroidery | Segment: apparel_embroidery |
| send_uk_signs_seq1.py | TaggIQ UK — Signs & Signage | Segment: signs |
| send_uk_print_promo_seq2.py | TaggIQ UK — Print & Promo | Day 5+ follow-up |
| (seq3-5 to follow same pattern) | | |

---

## Scrape Config Files

| File | Coverage |
|------|----------|
| config.py | Ireland (all 26 counties) — existing |
| config_uk.py | Full UK (391 queries) — created, use for future reference |
| config_london.py | London only (5 areas, full keyword coverage) — active |
| config_manchester.py | Manchester — create when Phase 2 starts |
| config_birmingham.py | Birmingham — create when Phase 2 starts |
| config_scotland.py | Glasgow + Edinburgh — create when Phase 3 starts |

---

## Checkpoint Gates

### Checkpoint 1 — London data review (before import)
- [ ] London scrape complete (all 5 areas)
- [ ] Email extraction run on London CSV
- [ ] Dedup against existing DB
- [ ] Present: total count, email coverage %, segment breakdown, sample rows
- [ ] Prakash approval to import

### Checkpoint 2 — Before first UK send
- [ ] UK campaigns created in DB
- [ ] London prospects imported
- [ ] Send script created + previewed
- [ ] Prakash approval to send

### Checkpoint 3 — After first 100 UK sends
- [ ] Check bounce rate (target <5%)
- [ ] Check open rate signal (track via reply volume)
- [ ] Check reply quality vs Ireland baseline
- [ ] Decide whether to stagger next UK campaign launch

---

## Fully Promoted UK — On Hold

Action required before launch:
- Contact FP corporate: confirm open UK territories
- Confirm Prakash's rights to recruit UK franchisees
- If approved: create separate FP UK campaign (franchise recruitment angle)
- Use prakash@fullypromoted.ie (Gmail SMTP, already configured)
- Do NOT launch before territory confirmation

---

## Kritno UK — Planning Phase

Prerequisites before launch:
- [ ] Set up Kritno email address (e.g., prakash@kritno.com or hello@kritno.com)
- [ ] Configure IMAP + SMTP in MailboxConfig
- [ ] Define Kritno ICP for UK (designers, agencies, print-heavy businesses)
- [ ] Write 5-email sequence from scratch
- [ ] Create /kritno-email-expert reply skill
- [ ] Earliest launch: Week 7-8 from now

---

## Status Tracking

Check anytime:
```
venv/bin/python manage.py shell -c "
from campaigns.models import Campaign, EmailLog, InboundEmail
from collections import Counter
for c in Campaign.objects.filter(product='taggiq').order_by('-created_at'):
    total = c.prospects.count()
    sent = EmailLog.objects.filter(campaign=c, status='sent').count()
    replies = InboundEmail.objects.filter(campaign=c).count()
    pending = InboundEmail.objects.filter(campaign=c, needs_reply=True, replied=False).count()
    print(f'{c.name}: {total} prospects | {sent} sent | {replies} replies | {pending} pending')
"
```
