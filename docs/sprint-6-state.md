# Sprint 6 Execution State

**Last updated:** 2026-04-13 (session in progress)
**Purpose:** Live execution tracker for Sprint 6. If the session dies mid-build, the next Claude reads this file + `docs/sprint-6-implementation-plan.md` and continues from the last unchecked task.

## How to resume if session is terminated

1. Read `docs/sprint-6-implementation-plan.md` for the full plan
2. Read this file for the exact current state
3. `git log --oneline -20` to see what's already committed
4. Find the first unchecked task below
5. Execute it, update this file, commit, move to next

## Phase 1A — Campaign build (dark code, no live impact)

- [x] 1A.1 — Migration 0016 (loom_url + personal_hook + flag + budget fields) ✓ applied laptop
- [x] 1A.2 — template_resolver LOOM_URL + PERSONAL_HOOK vars ✓
- [x] 1A.3 — Created Campaign `TaggIQ Warm Re-engagement Apr 2026` (id=0004101d-ec67-437c-a419-0c60e9352497), sending_enabled=False
- [x] 1A.4 — 4 EmailTemplate rows seeded (Seq 1-4 with {{PERSONAL_HOOK}}, {{LOOM_URL}} placeholders)
- [x] 1A.5 — CallScript row seeded, segment=us_ghost, is_active=True
- [x] 1A.6 — 15 prospects migrated, all personal_hook rendered, origin preserved in notes
- [x] 1A.7 — Nick Militello → not_interested, send_enabled=False
- [x] 1A.8 — Rendered all 15 Seq 1 emails via template_resolver, all hooks rendered correctly. Existing 18 campaigns still render same state.
- [ ] 1A.9 — Commit Phase 1A seeding (next)

## Phase 2A — Greenfield services (dark code, no live impact)

- [x] 2A.1 — `campaigns/services/conversation.py` ✓ (38 real-data tests pass)
- [x] 2A.2 — `campaigns/services/context_assembler.py` ✓ (injection-hardened, rule-based, budget-enforced)
- [x] 2A.3 — `campaigns/services/channel_timing.py` ✓ (Julie correctly blocked from call, Ifrah allowed)
- [x] 2A.4 — `campaigns/services/ai_budget.py` ✓ (F() atomic increment, month anchor reset)
- [x] 2A.5 — `campaigns/services/cacheable_preamble.py` ✓ (3 blocks: cached prefix + context + kicker)
- [x] 2A.6 — `manage.py eval_replies` ✓ (tested against ACEI, shows flat vs assembled diff)
- [x] 2A.7 — 38/38 tests pass via `manage.py sprint6_tests`
- [x] 2A.8 — Lisa v5 reply flow unchanged (handle_replies --product print-promo output identical)
- [x] 2A.9 — Laptop sequences unchanged (18 campaigns, same state as pre-Sprint-6)
- [x] 2A.10 — Doc update: service contracts in contextual-autonomous-marketing.md
- [ ] 2A.11 — Commit Phase 2A (next)

## Gated — do NOT execute in this run

- [ ] Phase 1B — Launch (waits on Loom URL from Prakash)
- [ ] Phase 2B — Wire context assembler into live code (waits on Phase 1 real data, 7 days post-launch)
- [ ] Phase 2C — Generalize to Lisa + FP after A/B validates

## Current step

**Phase 1A + 2A COMPLETE.** All greenfield services + campaign build shipped as dark code. 38 tests pass. Zero regression on existing campaigns verified.

**Blocked on:**
- Phase 1B (launch): waiting on Loom URL from Prakash
- Phase 2B (wire services into live code): waiting on 7+ days of Phase 1 real traffic data

## Decisions locked (do not re-litigate)

- Roster: 15 prospects (Nick removed as strategic contact, Julie excluded as active trial)
- Vapi: US-only (Ifrah), EU/UK waits for Telnyx
- Calendar link: `calendar.app.google/fzQ5iQLGHakimfjv7`
- Send window: Tue-Thu 09:00-17:00 Europe/Dublin
- From: `prakash@taggiq.com` (Zoho)
- Three features distributed one per email (Seq 1 supplier ordering / Seq 2 3-min quote / Seq 3 webstores)
- Context assembler: rule-based only, NO LLM calls
- Feature flag: Campaign.use_context_assembler defaults False
- Zero modifications to existing live code paths (handle_replies, send_ai_reply, send_sequences, place_calls)
- Prompt injection hardening via `<untrusted>` tags in context_assembler
- Budget ceiling per Organization with degrade-to-flat fallback
- Anthropic cache_control markers on static prefix in cacheable_preamble
- Shadow eval before flag flip (human review of paired drafts)
