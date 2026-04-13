# Sprint 7 Execution State

**Last updated:** 2026-04-13 (Phase 7.0 + Phase 7.1 core landed, Phase 7.2 wiring is next)
**Purpose:** Live execution tracker for Sprint 7. If the session dies mid-build, the next Claude reads this file + `docs/sprint-7-implementation-plan.md` and resumes from the last unchecked task.

## How to resume if session is terminated

1. Read `docs/sprint-7-implementation-plan.md` for the full plan
2. Read this file for exact current state
3. `git log --oneline -20` to see what's already committed
4. Find the first unchecked task in the phase tables below
5. Execute it, update this file, commit, move to next

---

## Phase 7.0 — Eval foundation (HARD BLOCKER on 7.1) — CORE DONE

- [x] 7.0.1 — Golden set starter (3 pairs × 3 products at `tests/golden_sets/*.json`). Expand to 15 before flag flip, tracked in notes.
- [x] 7.0.2 — `campaigns/services/eval_harness.py` + `manage.py eval_golden` command (commit `<see git log>`)
- [x] 7.0.3 — Baseline locked at `tests/golden_sets/baseline.json` (all 3 products 100% via stub generator — real baselines land in Phase 7.2 when the stub is replaced with live LLM calls)
- [x] 7.0.4 — Runbook in `docs/sprint-7-implementation-plan.md` Section 7

**Follow-ups:** Phase 7.2 replaces `_stub_generate()` in `eval_harness.py` with a real call through `cacheable_preamble.build()` so baselines become meaningful regression gates. Expand golden sets from 3 to 15 pairs each in parallel.

## Phase 7.1 — Data model + brain authoring (local only) — CORE DONE

- [x] 7.1.1 — Migration `0017_sprint7_product_brain.py` applied on local. Additive only: `product_brain`, `campaign_brain_override`, `ai_usage_log.brain_version`.
- [ ] 7.1.2 — `ProductBrain.clean()` JSONSchema validation (deferred to Phase 7.2 — brain_doctor already catches the common issues, full schema validation lands when brains become Prakash-editable via admin)
- [x] 7.1.3 — `campaigns/services/brain.py` loader (sole reader of `ProductBrain`, merges sparse overrides, Sonnet 4.6 job defaults)
- [x] 7.1.4 — `campaigns/services/rules_engine.py` pure-python evaluator (is_terminal, should_escalate, next_sequence_step, is_eligible_for_call, apply_reply_outcome, apply_call_outcome, is_win). Synthetic smoke test passes. Formal 15+ unit test suite deferred to Phase 7.2 alongside wiring tests.
- [x] 7.1.5 — `campaigns/services/next_action.py` composes brain + conversation state + channel_timing + rules_engine. Verified on real TaggIQ prospects.
- [x] 7.1.6 — TaggIQ `ProductBrain` seeded via `seed_sprint7_brains` command. Linked to new `PromptTemplate` row with platform voice rules (short — references `/taggiq-email-expert` skill for full detail).
- [x] 7.1.7 — FP Franchise `ProductBrain` seeded (same pattern, distinct escalation_rules favouring `fee/contract/royalty` keywords). Also print-promo brain seeded, linked to existing Lisa v6 PromptTemplate (untouched).
- [x] 7.1.8 — `brain_doctor` management command. Lints active brains, reports critical/warn/info findings, exits non-zero with `--strict`. Clean on all 3 brains.
- [x] 7.1.9 — `next_action_preview` shadow-mode command. Verified on TaggIQ Warm Re-engagement: 15 prospects routed (9 terminal, 6 waiting), 0 brain errors.

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

**Phase 7.0 + Phase 7.1 core shipped in one session on 2026-04-13.** Platform now has:
- Three live `ProductBrain` rows (taggiq, fullypromoted, print-promo) on local Postgres
- Brain loader + rules engine + next_action decision service
- Eval harness + golden sets (starter 3 pairs/product, 100% baseline)
- Shadow-mode preview + brain linter
- Zero impact on existing campaigns — all new code is dark (no live caller imports it yet)

**Commits landed this session:**
- `3640e1c` planning docs
- `5992608` lock open-question answers
- `<Phase 7.1 schema+services>` ProductBrain migration + brain.py + rules_engine.py + next_action.py
- `<Phase 7.0 + 7.1.6/7>` seed_sprint7_brains + eval_harness + eval_golden + golden sets + baseline
- `<Phase 7.1.8/9>` brain_doctor + next_action_preview

**Next actionable task: Phase 7.2.1 — wire `handle_replies` to the brain path behind `use_context_assembler` flag.** This is the first task that touches a live command. Acceptance:
- Flag=False campaigns run byte-identical to today (Lisa on EC2 must not change)
- Flag=True campaigns route through `cacheable_preamble.build()` with conversation context and record `brain_version` in `AIUsageLog`
- Regression test: run `send_sequences --dry-run` on both modes, diff output

**Resume pointer for a fresh session:**
1. `git log --oneline -15` — verify the Phase 7.1 commits are present
2. Read `docs/sprint-7-implementation-plan.md` Section 2.5 (feature flag strategy) and Section 4 Phase 7.2 table
3. Read `campaigns/management/commands/handle_replies.py` to understand the current (flag=False) path
4. Read `campaigns/services/cacheable_preamble.py` for the flag=True entry point
5. Start at 7.2.1. Work in tight commits.

## Decisions locked (do not re-litigate)

### Architecture (from CTO + AI architect review)
- **Brain contract:** `ProductBrain` (per-product) + `CampaignBrainOverride` (sparse per-campaign). No new columns on `Campaign` or `Prospect`.
- **Feature flag:** reuse existing `Campaign.use_context_assembler` from Sprint 6 (migration 0016). No new flag.
- **Model floor:** Sonnet 4.6 on all AI jobs, configurable per-brain via `jobs` JSON. Haiku explicitly rejected by Prakash 2026-04-13.
- **Decisioning:** rules engine only, no LLM on next-action. LLM reserved for content generation (reply, call opener, transcript analysis).
- **Judge model:** Opus 4.6 for golden set eval. ~$5/week cost.
- **Deployment surfaces:** Local Docker (TaggIQ + FP Franchise + FP BNI) and EC2 (`print-promo` via Lisa). Postgres 16 on both. No cross-host replication.
- **No impact on existing campaigns:** flag=False path is byte-sacred for the duration of Sprint 7. Any PR that changes it is a rejected merge.
- **Out of scope:** Kritno brain, UI for editing brains, attribution tokens, TCPA rules, public API, usage-based billing. All Phase 3.

### Prakash decisions 2026-04-13 (answering Section 9 open questions)
- **Overarching goal:** autonomous pipeline. No human approval step on normal flow. Humans surface only when `escalation_rules` fire. Sprint 7 is graded on "can Prakash close his laptop and the pipeline still runs for all products on the new brain path." Any design choice that reintroduces a routine human-in-the-loop step is wrong.
- **Golden set authoring (Q1):** Claude drafts all 30 pairs (15 TaggIQ + 15 print-promo) by pulling real inbound emails from both Postgres instances and writing ideal replies in the established voice. Prakash reviews asynchronously — no 90-minute live session required. Claude proceeds on the drafted set if review is pending.
- **Ifrah US test call (Q2):** not a Sprint 7 blocker. Skipped from the critical path. If Prakash wants to run it, he runs it himself or asks separately. Sprint 7 does not wait.
- **Brain authoring split (Q3):** Claude drafts both TaggIQ and FP Franchise brain JSON from `CLAUDE.md`, warm re-engagement plan, FP sales manual memory, and the voice rules in existing `PromptTemplate` rows. Prakash reviews. No human blocker on the draft.
- **Loom URL coupling (Q4):** decoupled. Phase 7.3.1 flips `use_context_assembler=True` on TaggIQ Warm Re-engagement when Phase 7.2 is green, independent of `sending_enabled`. Brain path is validated via shadow mode + dry runs until Loom lands. Real traffic starts when Loom lands — separate event.
- **EC2 rollout timing (Q5):** not a blocker. Default 3-day local observation window holds. Phase 7.4 proceeds to EC2 on schedule once local is stable, without waiting for TaggIQ Warm Re-engagement real traffic.

### Operating mode for Sprint 7 execution
- Claude works autonomously through phases. No mid-sprint approval checkpoints unless a task is genuinely blocked (external service, credentials, destructive action).
- Progress committed after every merged task. Prakash reviews commits, not pre-merge drafts.
- If Claude hits ambiguity, default choice: the one that reduces human intervention in the live pipeline.
