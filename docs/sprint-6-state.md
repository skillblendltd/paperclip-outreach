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

- [ ] 1A.1 — Migration 0016 (loom_url + personal_hook + flag + budget fields)
- [ ] 1A.2 — template_resolver LOOM_URL + PERSONAL_HOOK vars
- [ ] 1A.3 — Create Campaign row `TaggIQ Warm Re-engagement Apr 2026`
- [ ] 1A.4 — 4 EmailTemplate rows (Seq 1-4 with placeholders)
- [ ] 1A.5 — CallScript row (US-only Ifrah)
- [ ] 1A.6 — Migrate 15 prospects + personal_hook + origin preserved in notes
- [ ] 1A.7 — Nick Militello status → not_interested
- [ ] 1A.8 — Dry-run verification
- [ ] 1A.9 — Commit Phase 1A

## Phase 2A — Greenfield services (dark code, no live impact)

- [ ] 2A.1 — `campaigns/services/conversation.py`
- [ ] 2A.2 — `campaigns/services/context_assembler.py` (rule-based, injection-hardened)
- [ ] 2A.3 — `campaigns/services/channel_timing.py`
- [ ] 2A.4 — `campaigns/services/ai_budget.py`
- [ ] 2A.5 — `campaigns/services/cacheable_preamble.py`
- [ ] 2A.6 — `manage.py eval_replies` shadow eval command
- [ ] 2A.7 — Unit tests for services against real prospects
- [ ] 2A.8 — Regression check: Lisa v5 reply flow unchanged
- [ ] 2A.9 — Regression check: laptop sequences unchanged
- [ ] 2A.10 — Doc update: service contracts in contextual-autonomous-marketing.md
- [ ] 2A.11 — Commits Phase 2A (split per CTO commit structure)

## Gated — do NOT execute in this run

- [ ] Phase 1B — Launch (waits on Loom URL from Prakash)
- [ ] Phase 2B — Wire context assembler into live code (waits on Phase 1 real data, 7 days post-launch)
- [ ] Phase 2C — Generalize to Lisa + FP after A/B validates

## Current step

**In progress:** Committing the plan doc + state file. Phase 1A.1 is next.

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
