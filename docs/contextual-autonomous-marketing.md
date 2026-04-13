# Contextual Autonomous Marketing System — Architecture Vision

**Created:** 2026-04-13
**Status:** Vision doc, Phase 1 prove-it in progress (TaggIQ Warm Re-engagement campaign)
**Owner:** Prakash (product) + Claude (execution)
**Related:** `docs/taggiq-warm-reengagement-plan.md` (Phase 1 implementation)

## What this is

Paperclip Outreach is evolving from "a GTM engine Prakash uses for his three products" into a **contextual autonomous marketing system**: the first outbound engine that actually reads the prospect's conversation history before every touch, so email + call + reply feel like one continuous relationship instead of disjointed blasts.

**The test case:** The TaggIQ Warm Re-engagement campaign (Sprint 6, Phase 1). 15 prospects, 4 emails, 1 Vapi call, all driven by per-prospect context and persona-parameterized voice. If this works end-to-end, it becomes the template for TaggIQ × all campaigns, FP Ireland, Kritno, and eventually a standalone Paperclip product offering for design partners.

## Why this is different from existing tools

Every B2B outbound tool in the market falls into one of four buckets:

| Category | Example | Limitation |
|---|---|---|
| Mass email | Mailchimp, Apollo, Outreach.io | Variables like {{first_name}} only; no real personalization; each email standalone |
| Dialers | ConnectAndSell, Orum, Nooks | Agents read scripts; no memory of previous touches |
| CRM | HubSpot, Salesforce, Pipedrive | Stores state but doesn't *act* on it |
| AI SDR agents | 11x, AiSDR, Regie | Each touch is stateless; tone drifts across emails; conversations feel robotic when you read the thread end to end |

**What we're building collapses all four into one loop:**

1. Every interaction (email sent, reply received, call placed, voicemail left, webhook event) writes to one per-prospect timeline
2. Every new touch reads that timeline before drafting — so Email 3 references Email 2's topic naturally, the Vapi call references Monday's email specifically
3. Channel switches are seamless: a prospect who replied by email then picked up a call hears the caller reference the email
4. Voice consistency across channels: the email voice and the phone voice are derived from the same persona config, not hand-tuned separately

**The core differentiator:** existing products *fake* continuity with mail-merge variables. This system *actually reads the conversation* before writing the next message.

## Current state (what we already have)

From Sprints 1–5, we've accidentally built ~70% of the foundation:

| Capability | Status | File / model |
|---|---|---|
| Central `Prospect` with FK'd history (EmailLog, InboundEmail, CallLog, AIUsageLog, notes) | ✅ | `campaigns/models.py` |
| Multi-tenant org/product/campaign structure | ✅ | Organization → Product → Campaign → Prospect |
| Per-product voice rules in DB (PromptTemplate) | ✅ | Lisa v5 `print-promo`, ~8K chars voice-only |
| Pre-send safety rails (price / bounce / length detectors) | ✅ | `campaigns/services/reply_audit.py` |
| Retry budget + manual-review escalation | ✅ | `InboundEmail.ai_attempt_count`, max 5, then notes flag |
| Email reply autonomy with DB context | ✅ | `send_ai_reply` command, v5 |
| Vapi integration with webhook → CallLog | ✅ | `place_calls` command, infrastructure in place |
| AIUsageLog for per-tenant cost attribution | ✅ | Wired in `send_ai_reply` |
| Org-agnostic contract (voice in DB, mechanics in code) | ✅ | `handle_replies._build_execution_preamble`, v5 refactor |

**The foundation is surprisingly close.** Sprint 5 v5 was unintentionally the backbone — we didn't realize at the time that persona-parameterized recipes, DB PromptTemplates, pre-send blocking, and retry budgets were all load-bearing pieces of a future contextual marketing system. They were.

## Gap analysis (what's missing)

| # | Gap | Severity | Why it matters |
|---|---|---|---|
| 1 | **Conversation aggregator** — one query that returns a chronological timeline of every event for a prospect | HIGH | Every touch SHOULD start with "read the last 14 days" but today we don't |
| 2 | **Context assembler service** — given prospect, return conversation summary in N tokens | HIGH | Without this, prompts dump raw history → bloat and lose focus |
| 3 | **Cross-channel timing coordination** — don't call after a recent reply, don't email after a recent call | HIGH | Breaks conversation continuity when channels collide |
| 4 | **Dynamic Vapi script generation** — read prospect history to build the first_message | HIGH | Today's `first_message` is a static string, can't reference the last email specifically |
| 5 | **Human handoff UX** — escalation path when the system hits something it shouldn't handle | MED | Blocks automation on high-value prospects |
| 6 | **Attribution layer** — which touch caused the reply | MED | Can't iterate what you can't measure |
| 7 | **Consent/compliance tracking** — TCPA (US calls) and GDPR lawful basis (EU emails) | MED | Legal risk once volume grows |
| 8 | **Readiness score** — signal-driven next-touch recommendation | LOW | Nice-to-have, not critical path |

**Gaps 1–4 are the critical path to realizing the vision.** Gaps 5–8 are Phase 3 polish.

## Phased plan

### Phase 1 — Prove-it (1 week, in progress)

**Goal:** Ship ONE campaign end-to-end with real prospects. Don't generalize. Don't build the context assembler yet. Prove the concept works on real traffic, measure the result, learn where it breaks.

**Deliverable:** TaggIQ Warm Re-engagement campaign live (see `docs/taggiq-warm-reengagement-plan.md`)

**Scope:**
- 15 prospects
- 4 sequence emails (Seq 1 supplier ordering / Seq 2 3-min quote / Seq 3 webstores + breakup / Seq 4 soft close)
- 1 Vapi call (Ifrah, US — only US-scoped until Telnyx Irish number lands)
- PERSONAL_HOOK per prospect (pre-populated, flat template, not dynamically assembled yet)
- LOOM_URL campaign-level variable (blocked on Prakash recording the Loom)
- Existing reply pipeline handles any responses (manual review for TaggIQ until DB PromptTemplate exists for that product)

**Success criterion:** 3+ replies out of 15 prospects within 14 days, at least 1 demo booked.

**What we learn:**
- Where real traffic breaks assumptions
- Whether PERSONAL_HOOK as a flat variable is enough, or whether prospects notice the canned feel
- How often cross-channel timing conflicts happen in practice
- What Prakash manually corrects when reviewing replies — inputs to Phase 2

**What we deliberately defer:**
- Conversation model (Phase 2)
- Context assembler (Phase 2)
- Dynamic Vapi scripting (Phase 2)
- TaggIQ/FP Franchise reply prompts (Phase 2)
- Attribution layer (Phase 3)
- Human handoff UX (Phase 3)

### Phase 2 — Conversation model + context assembler (1–2 weeks, after Phase 1 ships)

**Goal:** Build the mini-CRM memory layer so every future touch has a real conversation memory, not a flat variable.

**New components:**

1. **`campaigns/services/conversation.py`**
   - `get_prospect_timeline(prospect, days=30)` → chronological list of all events (EmailLog sent, InboundEmail received, CallLog placed, ScriptInsight captured, manual notes)
   - `get_last_topic(prospect)` → one-line summary of the most recent outbound topic (for Vapi opener generation)
   - `get_conversation_state(prospect)` → structured summary: {last_outbound_at, last_inbound_at, last_channel, open_question, expressed_pain, status_history[]}

2. **`campaigns/services/context_assembler.py`**
   - `build_context_window(prospect, max_tokens=2000)` → picks the N most-relevant events (recent + high-signal) and formats them for injection into a PromptTemplate
   - Priority order: expressed pain signals > open questions > recent replies > recent outbound > older history
   - Token budget enforced; oldest events dropped first

3. **Integration with `handle_replies._build_execution_preamble`**
   - Instead of only injecting persona + product, also inject `[CONVERSATION CONTEXT]\n{assembled history}\n`
   - The voice rules become *how* to respond; the context becomes *what* the conversation is about

4. **Integration with `place_calls`**
   - Before Vapi call, call `conversation.get_last_topic(prospect)` and build a dynamic first_message:
     ```
     "Hi {fname}, this is Prakash from TaggIQ. I sent you a note about
     {last_topic} on {last_outbound_day}, wanted to make sure it didn't
     get lost in your inbox. Got 60 seconds?"
     ```
   - Webhook returns of voicemail/answer/no-answer flow back into the Conversation for the next touch

5. **Cross-channel timing locks**
   - Before any outbound, check `conversation.get_last_inbound_at()` — skip if within 24h
   - Before any call, check `conversation.get_last_email_at()` — require ≥48h gap
   - Config lives at Campaign level (per-tenant override)

**Success criterion:** A prospect who received Seq 1 Monday morning, replied Tuesday afternoon, and is then cold-called Wednesday morning hears the Vapi AI reference the reply specifically — not the original email.

### Phase 3 — Productize + hardening (3–6 weeks)

**Goal:** Turn the system into something that can be sold as a product, either as Paperclip-as-a-service to design partners or as "powered by" technology inside TaggIQ.

**Scope:**
- Org-level isolation audit (not just convention — middleware-enforced)
- UI for prompt template management, conversation timeline, per-prospect state
- Per-org pricing model (usage-based on AIUsageLog totals)
- Integration API ("send me your lead list as JSON, I'll run the campaign")
- Attribution layer (UTM-style tokens, reply attribution)
- Human handoff UX (escalation queue, oncall rotation)
- Consent tracking (TCPA + GDPR lawful basis fields on Prospect + Suppression)
- Readiness score (signal-driven next-touch recommendation)
- Multi-language voice rules (PromptTemplate already supports it, needs UI)

**Go-to-market:**
- Existing TaggIQ design partners (Print RFT, Promotex.ie, Keynote, Embroidered Horse, Hämeen Mainostuote) become Paperclip design partners
- Two-product story: TaggIQ = POS platform, Paperclip = autonomous outbound engine. Natural cross-sell.
- Pricing: usage-based on AIUsageLog cost + markup, or flat per-seat

## Known risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Tone consistency breaks across channels** — email ≠ phone voice, prospect smells a robot | HIGH | Same PromptTemplate drives both. Vapi assistant prompt derived from voice rules in Phase 2. |
| **Cross-channel conflicts** — call dials during ongoing reply thread | HIGH | Phase 2 timing locks |
| **Cost runaway** — context assembly inflates prompts, bills balloon | MED | AIUsageLog already tracks; add per-tenant budget alerts in Phase 2 |
| **Compliance trap** — TCPA (US calls no consent), CAN-SPAM, GDPR | MED | Suppression model already scopes per-product; add state-specific call-time restrictions Phase 3 |
| **Voice of God** — Claude responses converge across personas over time | MED | PromptTemplate per product is the firewall; separate DB rows enforce separate voices |
| **"Is this AI?" challenge** — prospect asks directly | MED | Policy: never lie. "I'm Prakash's assistant writing on his behalf." Honesty beats denial. |
| **Attribution noise** — can't tell which touch caused the reply | LOW | Phase 3 — campaign/sequence tokens in email footers |

## Non-negotiables

**One architectural firewall from CTO review:** Before Phase 2 ships, add the `Conversation` service layer as the boundary. Every feature that needs "what happened with this prospect" goes through `conversation.get_prospect_timeline()` and nothing else. Do not build 10 different versions of "get recent touches" scattered across commands. The service boundary is what keeps the system maintainable as it grows.

**Product policy:** PromptTemplate voice rules are the source of truth for persona identity. If the email says "Lisa from Fully Promoted Dublin", the Vapi call does too, derived from the same row. Never let two channels drift into their own voice definitions.

## Relation to the three products

| Product | Role in contextual marketing system |
|---|---|
| **TaggIQ** | The first product to fully use this system (Phase 1 = TaggIQ Warm Re-engagement). TaggIQ sales is the prove-it case. |
| **Fully Promoted Ireland** | Already uses the system for Lisa (print-promo) replies via v5 pipeline. Needs Prakash voice ported to DB PromptTemplate to close the autonomy loop for FP Franchise + BNI. |
| **Kritno** | Future product. Will be the third persona in the system. Greenfield for a new voice + campaign structure from day 1. |
| **Paperclip Outreach** | The platform itself. Eventually sellable as a standalone product to design partners. Today it's internal GTM tooling. |

## Open questions (revisit after Phase 1)

1. Should the Conversation be a separate model, or computed on-the-fly from existing FKs? → Probably computed. No new writes, just a read service over existing data. Cheaper, no migration.
2. Do we need per-org Vapi phone numbers or can one number serve all? → Per-org, because caller ID must match the org branding. Telnyx provisioning is the gating factor.
3. How do we handle multi-org within one email thread (e.g., a prospect is in both a TaggIQ campaign and an FP campaign)? → Suppression is already product-scoped. Conversation aggregator should filter by product_slug.
4. Should the conversation timeline include *outbound* emails the prospect never opened? → Yes. Every touch is context, whether received or not.
5. What's the retention policy on Conversation data? → Match GDPR 2-year default. Suppress on opt-out, purge on explicit request.

## Decision log

- **2026-04-13** Framing emerged mid-session while building TaggIQ Warm Re-engagement campaign. Prakash reframed the work as "contextual autonomous marketing system test case" rather than one-off campaign.
- **2026-04-13** CTO architect review: validated vision, identified 8 gaps (4 critical), proposed 3-phase plan. Approved with the Conversation service layer firewall as non-negotiable before Phase 2.
- **2026-04-13** Phase 1 scope locked: 15 TaggIQ prospects, 4 emails, 1 Vapi call (Ifrah US only). Success criterion: 3+ replies, 1+ demo booked in 14 days.
- **2026-04-13** Phase 2 deferred until Phase 1 has 7+ days of real traffic.

## Resume instructions for next session

1. Read this doc AND `docs/taggiq-warm-reengagement-plan.md`
2. Check Phase 1 status — Loom URL provided? Campaign shipped? Replies coming in?
3. If Phase 1 is live and has real data → start Phase 2 planning: Conversation model, context assembler, timing locks, dynamic Vapi scripting
4. If Phase 1 is still blocked → resume Phase 1 per `docs/taggiq-warm-reengagement-plan.md`
5. Never break the Conversation service firewall rule when adding new features
