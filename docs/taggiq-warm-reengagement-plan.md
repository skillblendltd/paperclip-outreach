# TaggIQ Warm Re-engagement Campaign (Sprint 6 / Phase 1)

**Last updated:** 2026-04-13
**Status:** In-progress, paused mid-Phase-A (model changes) pending session resume
**Owner:** Prakash (decisions), Claude (execution)
**Purpose:** First campaign to exercise the contextual autonomous marketing system end-to-end. See `docs/contextual-autonomous-marketing.md` for the bigger vision this campaign is a prove-it case for.

## Goal

Re-engage 15 warm TaggIQ prospects (demo_scheduled, engaged, or explicitly interested) across a 4-email sequence + 1 Vapi call, with the three new TaggIQ capabilities as the narrative hook:

1. Direct supplier order submission (PO → supplier in one click)
2. Decoration options pulled per garment from supplier catalogs
3. Branded webstores for customers

**Success criterion:** 3+ replies within 14 days, at least 1 demo booked.

## Campaign spec (to be created in DB)

| Field | Value |
|---|---|
| Name | `TaggIQ Warm Re-engagement Apr 2026` |
| Product | `taggiq` |
| from_email | `prakash@taggiq.com` (Zoho — personal, better for replies) |
| from_name | `Prakash Inani` |
| reply_to_email | `prakash@taggiq.com` |
| sending_enabled | True (after Loom URL set) |
| calling_enabled | True (first TaggIQ campaign to use Vapi) |
| send_window_timezone | `Europe/Dublin` |
| send_window_hours | 09:00–17:00 |
| send_window_days | Tue, Wed, Thu (1,2,3) |
| max_emails_per_day | 10 |
| min_gap_minutes | 5 |
| batch_size | 10 |
| max_calls_per_day | 5 (Vapi) |
| max_calls_per_prospect | 2 |
| vapi_assistant_id | (use existing env VAPI_ASSISTANT_ID) |

## Sequence (4 emails + 1 call)

| Step | When | Channel | Headline feature | Purpose |
|---|---|---|---|---|
| Seq 1 | Day 0 Tue | Email | **Direct supplier order submission** | "I built the thing you asked about" — Loom + personal hook |
| Call 1 | Day 2 Thu | Vapi | — | 1 call only: Ifrah (US). EU/UK prospects wait for Telnyx Irish number. |
| Seq 2 | Day 4 Fri | Email | **Decoration options (3-min quote narrative)** | Quote-speed proof point, borrows exact LinkedIn phrasing |
| Seq 3 | Day 7 Mon | Email | **Branded webstores + breakup** | Complete-platform close, one-line reply ask |
| Seq 4 | Day 14 Mon | Email | — | Soft final touch, "what would it take?" question |

## Email copy (drafts — needs Loom URL + review)

### Seq 1 — Subject: `New since you signed up — order suppliers directly from TaggIQ`

```
Hi {{FNAME}},

{{PERSONAL_HOOK}}

Quick reason I'm reaching out: we just shipped something that changes
the math for how shops like {{COMPANY}} quote and order.

You can now submit purchase orders directly to suppliers from inside
TaggIQ — no re-keying into portals, no spreadsheets, no email-and-pray.
Pick a product, add to quote, submit the PO, done.

I recorded a 90-second demo of the full flow here: {{LOOM_URL}}

If it's interesting, reply with a time that suits and I'll walk you
through it live in your own data. If not, no hard feelings — I won't chase.

Prakash
(Founder, TaggIQ. Also runs Fully Promoted Kingswood — built this because
I needed it myself.)
```

### Seq 2 — Subject: `From "I need 200 polos" to quote in 3 minutes`

```
{{FNAME}}, quick follow-up on my last note.

Here's one thing the new supplier integration makes possible — what used
to be a quoting afternoon is now a 3-minute job.

Search "polo" in SourceIQ. Filter by supplier, price range, available
colours. Select the perfect polo. Click "Add to Quote." Pick the
decoration method (embroidery, DTG, screen, vinyl — scoped automatically
per garment). Email the customer a live presentation link.

Total time: under 3 minutes. Same accuracy. Better presentation.
A fraction of the effort.

That's not a demo scenario. That's a Tuesday afternoon at {{COMPANY}}.

Happy to screen-share for 15 min so you see it on your own products.
Tuesday or Wednesday morning?

Prakash
```

### Seq 3 — Subject: `Closing your demo request?`

```
{{FNAME}}, tidying up open demo requests this week. Should I close
yours, or is there still a fit for TaggIQ at {{COMPANY}}?

One more thing before I stop emailing — we also shipped branded webstores.
Your customers place their own orders from a private store you set up in
10 minutes, you approve, we submit to the supplier. Quote, decorate,
order, webstore — all in one place.

If TaggIQ isn't the right fit right now, a one-line "not now" reply helps
me stop bothering you and I'll respect it.

If timing's just bad, tell me when to circle back and I'll respect it to
the day.

Prakash
```

### Seq 4 — Subject: `One last check-in`

```
{{FNAME}}, last one from me. If TaggIQ ever becomes relevant at
{{COMPANY}}, you've got my direct line — prakash@taggiq.com. No hard
feelings either way.

If there's ever a future version of TaggIQ that would make sense, I'd
rather hear it from you in one email than guess. What would it take?

Prakash
```

## Vapi call script (CallScript row, US-only for now)

```
Hi {{FNAME}}, this is a message from Prakash Inani at TaggIQ.

I sent you a note about supplier order submission earlier this week.
You had requested a demo back in March, and I wanted to make sure
this update didn't get lost in your inbox.

If you have a minute now I can give you the 90-second version, or if
easier I can set up a 15-minute walkthrough whenever works for you.

Are you free for a quick chat, or would later today suit better?
```

- **US-only scoping** until Telnyx Irish number is live (current Vapi uses US caller ID)
- Max 2 attempts per prospect, 48h gap between attempts
- Webhook → CallLog → auto-update prospect status on "demo_booked" outcome

## Roster — 15 prospects

### Tier 2 Ghosts (8)

| # | Name | Company | Phone | Personal hook |
|---|---|---|---|---|
| 1 | Tuomas Karppinen | Printtivaate, Finland | +358 29 0025051 | You sent me a detailed list of requirements back in March — ecommerce, design tool, supplier integration — and I disappeared. That's on me. |
| 2 | Ian Holligan | M-Grafix, Barbados | — | You were warm on the demo back in March then things went quiet on my end. Quick update from Dublin... |
| 3 | Jordan Singh | Your Brand Solution, Leicester | — | You mentioned wanting to join the best-practices group — that's still on. Before I loop you in, quick thing you asked about... |
| 4 | Robert Šmid | Promoluks, Ljubljana | — | Your note back in March stuck with me — you went from casual chat to "let me see it" in one email. |
| 5 | Katy Pastoors | Creative Promo, Australia | — | You offered to do a BNI 1-on-1 around the demo — I still owe you one. |
| 6 | David Pollard | Pocatello US | — | You requested a demo via the TaggIQ site and I never came back. That's my fault. |
| 7 | Yann | Promo Média, Canada | — | You came in via the TaggIQ website — direct demo request, no BNI in between. I owe you an actual demo. |
| 8 | Rachel | Karst, US | — | Your demo request came in via the TaggIQ website in late March. I never came back. That's my fault. |
| 9 | **Ifrah ★** | Bulk Swag, US | **+1 703 574 3217** | Direct website demo request from Bulk Swag — US-based, which means this next thing matters especially for you. |

### Tier 3 Engaged Priority (6)

| # | Name | Company | Phone | Personal hook |
|---|---|---|---|---|
| 10 | Jon Lambert | Zest Branding, Ireland | +353 87 272 3700 | You've been using TaggIQ in trial and I still owe you a follow-up on the feedback you left. |
| 11 | Vanessa Calero | GoSwag, US | — | You described your quote-then-artwork-approval flow in detail — it's exactly the workflow we built around. |
| 12 | Martina Potts | Minuteman Press Myrtle Beach | — | You mentioned you "do your best through email" for quotes — that line stuck with me because it's the exact pain we built TaggIQ to kill. |
| 13 | Tonia Namuli Ssempa | Uganda | — | You asked "why do you ask?" when I wrote — fair question. Since then we built what I was probing for. |
| 14 | Darren Lander | MTPromo, London | — | You said "follow up after April 9" — so here I am. |
| 15 | Ian Abrahams | Treacle Factory | — | You had to cancel the demo last minute in March and the reschedule email never landed with you. No hard feelings. |

**Vapi call target:** Ifrah (Bulk Swag) only in this pass. Jon Lambert is Irish — skip call until Telnyx is live.

## Explicitly EXCLUDED from this campaign

| Prospect | Reason | Action |
|---|---|---|
| Paul Rivers (Print RFT) | Design partner — Solopress/Clothes2Order API integration | Manual founder check-in this week |
| Sharon Bates (Keynote Marketing) | Design partner — Impression Europe API, chasing Reece | Manual founder check-in |
| Sue Metcalf (Embroidered Horse) | Design partner — post-demo conversion | Manual "what's blocking real orders?" check |
| Jere Putkisaari (Hämeen Mainostuote) | Design partner — Stricker/Midocean integration | Manual SourceIQ update |
| Declan Power (Promotex.ie) | Design partner — reseller/white-label | **Phone call**, not email |
| **Julie Keene (Get Uniforms & More)** | Signed up for trial 2026-04-08, went silent | **Nudge already sent 2026-04-13** via `transfer/nudge_julie.py`, status updated to `engaged` |
| Cian (Textile Print & Embroidery) | Already in trial | Trial-specific conversation |
| Nigel Smith (Supermotion) | Bereaved | Manual soft touch end of month |
| Simon Raybould (Print Crew) | Explicitly said "not interested in TaggIQ" | BNI relationship nurture only |
| **Nick Militello (Omnipher/Tekweld)** | Not a potential customer per Prakash — strategic contact only | Update status to `not_interested` with note "Tekweld network, not a buyer" |

## What's been DONE

- ✅ Julie Keene nudge sent 2026-04-13 (`transfer/nudge_julie.py`, status → engaged)
- ✅ 3 capabilities aligned with LinkedIn phrasing (verified from `/taggiq-marketing/LINKEDIN_POSTS.md`)
- ✅ "3-minute quote" canonical number locked in for Seq 2
- ✅ Vapi infrastructure confirmed (VAPI_API_KEY / ASSISTANT_ID / PHONE_NUMBER_ID all set)
- ✅ Phone coverage audited (11 of 59 warm TaggIQ prospects have phones, only Ifrah in US → only Vapi candidate)

## What's IN PROGRESS (paused)

- ⏸️ Phase A: Model changes (`Campaign.loom_url`, `Prospect.personal_hook`) — not yet started
- ⏸️ `template_resolver.py` variable additions (LOOM_URL, PERSONAL_HOOK)
- ⏸️ Campaign row creation
- ⏸️ 4 EmailTemplate rows (Seq 1-4 drafts above, need LOOM_URL substituted)
- ⏸️ CallScript row for Ifrah
- ⏸️ Prospect migration (15 prospects → new campaign, preserve original in notes)
- ⏸️ Dry-run verification

## What's BLOCKED on Prakash

| # | Item | Urgency |
|---|---|---|
| 1 | **Loom video URL** (90 sec, supplier ordering flow) | HIGH — unblocks Seq 1 |
| 2 | Pilot customer name for Seq 2 (or default to Fully Promoted Kingswood) | LOW — default works |

## Approved decisions (locked)

- Roster of 15 approved (Nick removed, Julie excluded because she's active trial, Cian excluded because in trial)
- Vapi US-only (wait for Telnyx for EU/UK)
- Calendar link: `calendar.app.google/fzQ5iQLGHakimfjv7` (reused from other campaigns)
- Send schedule: Tue-Thu, 09:00-17:00 Europe/Dublin
- From: `prakash@taggiq.com` (Zoho)
- Three features distributed one per email (Seq 1 supplier ordering / Seq 2 decoration options / Seq 3 webstores)

## Open architectural questions (defer to Phase 2)

- Should the Seq 1 body be dynamically generated from prospect conversation history (context assembler), or stay as a flat template with PERSONAL_HOOK variable? **Decision: flat template for Phase 1. Context assembler is Phase 2.**
- Should the Vapi script be dynamically generated per prospect referencing Seq 1's exact topic? **Decision: static first_message for Phase 1. Dynamic scripting is Phase 2.**
- Should TaggIQ replies get a DB PromptTemplate (like Lisa v5) before this campaign goes out? **Decision: NO for Phase 1. Prakash will handle the first 5-10 replies manually via `/taggiq-email-expert` to tune the voice before porting to DB.**

## Resume instructions for next session

1. Read this doc AND `docs/contextual-autonomous-marketing.md` for context
2. Check whether Prakash has provided the Loom URL since last session
3. If yes → continue Phase A: add `Campaign.loom_url` + `Prospect.personal_hook` fields, migrate, update template_resolver, create campaign + templates + script + migrate 15 prospects, dry-run, await Tuesday launch
4. If no → remind Prakash the Loom is the only blocker, confirm roster still valid, do not proceed with build
5. After Phase 1 launches, monitor reply flow for 7 days, then start Phase 2 (Conversation + context assembler) per `contextual-autonomous-marketing.md`

## Files

- `docs/taggiq-warm-reengagement-plan.md` (this doc)
- `docs/contextual-autonomous-marketing.md` (architectural vision)
- `transfer/nudge_julie.py` (completed, one-off Julie activation email)
- `CLAUDE.md` "TaggIQ Warm Re-engagement" section (to be added)
