# Sprint 7 Execution State

**Last updated:** 2026-04-13 (planning complete, execution not started)
**Purpose:** Live execution tracker for Sprint 7. If the session dies mid-build, the next Claude reads this file + `docs/sprint-7-implementation-plan.md` and resumes from the last unchecked task.

## How to resume if session is terminated

1. Read `docs/sprint-7-implementation-plan.md` for the full plan
2. Read this file for exact current state
3. `git log --oneline -20` to see what's already committed
4. Find the first unchecked task in the phase tables below
5. Execute it, update this file, commit, move to next

---

## Phase 7.0 — Eval foundation (HARD BLOCKER on 7.1)

- [ ] 7.0.1 — Capture golden set fixtures (15 pairs × 2 products)
- [ ] 7.0.2 — Build `eval_harness.py` + `eval_golden` management command
- [ ] 7.0.3 — Lock baseline scores, commit `tests/golden_sets/baseline.json`
- [ ] 7.0.4 — Runbook entry in `sprint-7-implementation-plan.md` Section 7

## Phase 7.1 — Data model + brain authoring (local only)

- [ ] 7.1.1 — Migration `0017_product_brain_and_overrides.py`
- [ ] 7.1.2 — `ProductBrain.clean()` JSONSchema validation
- [ ] 7.1.3 — `brain.py` loader service
- [ ] 7.1.4 — `rules_engine.py` pure-python evaluator (15+ unit tests)
- [ ] 7.1.5 — `next_action.py` decide_next_action service
- [ ] 7.1.6 — Seed TaggIQ `ProductBrain` + `PromptTemplate`
- [ ] 7.1.7 — Seed FP Franchise `ProductBrain` + `PromptTemplate`
- [ ] 7.1.8 — `brain_doctor` management command
- [ ] 7.1.9 — Shadow mode: `next_action_preview --campaign X`

## Phase 7.2 — Wire executors through the brain (local only)

- [ ] 7.2.1 — `handle_replies` feature flag branch (cacheable_preamble path)
- [ ] 7.2.2 — `send_ai_reply` budget gate wiring
- [ ] 7.2.3 — `vapi_opener.py` + `place_calls` dynamic first_message
- [ ] 7.2.4 — `send_sequences` timing locks
- [ ] 7.2.5 — Vapi webhook → brain state machine
- [ ] 7.2.6 — Escalation handoff via `escalation_rules`
- [ ] 7.2.7 — Full regression on flag=False (byte-identical)
- [ ] 7.2.8 — Golden set re-run on flag=True (>= baseline)

## Phase 7.3 — Local rollout

- [ ] 7.3.1 — Flip `TaggIQ Warm Re-engagement Apr 2026` to flag=True (blocked on Loom URL)
- [ ] 7.3.2 — 3-day observation + daily rollout log entries
- [ ] 7.3.3 — Journey timeline admin view
- [ ] 7.3.4 — `campaign_kpis` management command
- [ ] 7.3.5 — Flip second local campaign after day 3

## Phase 7.4 — EC2 rollout

- [ ] 7.4.1 — Deploy code + migration 0017 to EC2
- [ ] 7.4.2 — 24h EC2 burn-in on flag=False (zero diff)
- [ ] 7.4.3 — Seed FP print-promo `ProductBrain` on EC2
- [ ] 7.4.4 — Flip smallest EC2 campaign to flag=True
- [ ] 7.4.5 — 3-day EC2 observation + rollout log

## Phase 7.5 — Cleanup

- [ ] 7.5.1 — Update `docs/sprint-plan.md` status table
- [ ] 7.5.2 — Update `CLAUDE.md` v2 status — Sprint 7 DONE
- [ ] 7.5.3 — Write `docs/sprint-8-kickoff.md`
- [ ] 7.5.4 — Deprecate `_build_execution_preamble` comment

---

## Current step

**Planning phase complete.** Doc committed at planning state. Execution blocked on Prakash approval to start Phase 7.0 (golden set capture, ~90 min of Prakash time) and answers to Section 9 open questions in the implementation plan.

**Blocked on:**
- Phase 7.0.1 — Prakash availability for golden set review session
- Phase 7.3.1 — Loom URL for TaggIQ Warm Re-engagement (also blocks Sprint 6 Phase 1B, independent)

## Decisions locked (do not re-litigate)

- **Brain contract:** `ProductBrain` (per-product) + `CampaignBrainOverride` (sparse per-campaign). No new columns on `Campaign` or `Prospect`.
- **Feature flag:** reuse existing `Campaign.use_context_assembler` from Sprint 6 (migration 0016). No new flag.
- **Model floor:** Sonnet 4.6 on all AI jobs, configurable per-brain via `jobs` JSON. Haiku explicitly rejected per Prakash 2026-04-13.
- **Decisioning:** rules engine only, no LLM on next-action. LLM reserved for content generation (reply, call opener, transcript analysis).
- **Judge model:** Opus 4.6 for golden set eval. ~$5/week cost.
- **Deployment surfaces:** Local Docker (TaggIQ + FP Franchise + FP BNI) and EC2 (`print-promo` via Lisa). Postgres 16 on both. No cross-host replication.
- **Rollout order:** Local first (Warm Re-engagement), 3-day observation, EC2 only after local proves out.
- **No impact on existing campaigns:** flag=False path is byte-sacred for the duration of Sprint 7. Any PR that changes it is a rejected merge.
- **Out of scope:** Kritno brain, UI for editing brains, attribution tokens, TCPA rules, public API, usage-based billing. All Phase 3.
