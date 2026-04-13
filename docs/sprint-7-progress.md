# Sprint 7 Execution State

**Last updated:** 2026-04-13 (Phase 7.2 + bonus 7.3.3/7.3.4 landed, CTO-approved; Phase 7.3 flag-flips + 7.4 EC2 rollout are time-gated)
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

## Phase 7.2 — Wire executors through the brain (local only) — DONE, CTO-APPROVED

- [x] 7.2.1 — `handle_replies` feature flag branch (`0b5f8a0`)
- [x] 7.2.2 — `send_ai_reply` budget gate + brain_version on AIUsageLog (`7db4865`)
- [x] 7.2.3 — `vapi_opener.py` (NEW) + `place_calls` dynamic first_message (`e983178`)
- [x] 7.2.4 — `send_sequences` timing locks (`43fe6ce`)
- [x] 7.2.5 — Vapi webhook → brain state machine (`8319e48`)
- [x] 7.2.6 — Escalation handoff via `escalation_rules` (`79831aa`)
- [x] 7.2.7 — Regression checks command `sprint7_regression`, 3/3 structural pass (`4b666e9`) — **behavioral Django TestCase coverage still owed before Phase 7.4**
- [x] 7.2.8 — Golden set harness re-run (`2b2522f`) — **scores from rule_based_stub generator only; NOT a real regression signal. Live-LLM upgrade blocked on anthropic SDK + API key in test env. `TODO(sprint7-phase7.2.8)` marker in `eval_harness.py` with exact wiring recipe. Must run once with real LLM before Phase 7.4.**

**CTO architect review (2026-04-13):** APPROVED for merge. All contract items pass (byte-sacred flag=False, no product-slug conditionals, module boundaries held, AIUsageLog.brain_version wired). One IMPORTANT follow-up: promote the `InboundEmail.objects.exists()` dispatch probe in handle_replies to a `conversation.any_flagged_inbound_for_product()` helper. See CTO conditions in "Phase 7.3/7.4 gate conditions" below.

## Phase 7.3 — Local rollout — partially done; flag flips + observation are time-gated

- [ ] 7.3.1 — Flip `TaggIQ Warm Re-engagement Apr 2026` to flag=True (**HUMAN ACTION** — flag flip decoupled from Loom per locked decisions, but Prakash should flip explicitly after reviewing this doc)
- [ ] 7.3.2 — 3-day observation + daily rollout log entries (**TIME-GATED** — cannot complete in a session; requires real cron cycles + reply traffic)
- [x] 7.3.3 — Journey timeline admin view (`8ac47fe`) — `ProspectAdmin` custom URL `/journey/`, product-agnostic, read-only
- [x] 7.3.4 — `campaign_kpis` management command (`b1b38f0`) — prints sends/replies/interested/demos/escalations/cost per campaign
- [ ] 7.3.5 — Flip second local campaign after day 3 (**TIME-GATED**)

### Phase 7.3/7.4 gate conditions (CTO-mandated)

Before flipping any EC2 campaign to flag=True in Phase 7.4:
1. **Golden set must be re-run with a real LLM** (not the `rule_based_stub`) against the new brain path. Upgrade `eval_harness._stub_generate` using the TODO recipe; scores must meet the Phase 7.0 baseline.
2. **Behavioral Django TestCase coverage** of the flag=True branches must land — structural `sprint7_regression` is insufficient for EC2 production.
3. **Three consecutive clean observation days on local** with at least one flag=True campaign actually handling real reply traffic.
4. **Promote `InboundEmail.objects.exists()` dispatch probe** in `handle_replies._invoke_with_contextual_prompt` to `conversation.any_flagged_inbound_for_product(product)` helper.

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

**Phase 7.2 + bonus Phase 7.3.3/7.3.4 shipped on 2026-04-13 (second session of the day).** Platform now has:
- All live commands (handle_replies, send_ai_reply, place_calls, send_sequences, vapi_webhook) gated behind `Campaign.use_context_assembler` with flag=False paths byte-identical
- New `vapi_opener.py` service generating Sonnet-4.6 call openers from conversation history, logging to AIUsageLog
- Escalation handoff writes `ESCALATION: {reason}` to `Prospect.notes` and structured logs on brain-signalled hot leads
- Prospect journey timeline admin view (read-only, product-agnostic)
- `campaign_kpis` management command for per-campaign rollups
- CTO-approved merge; no blockers; structural regression command passes 3/3

**Commits landed this session (10):**
- `0b5f8a0` 7.2.1 handle_replies contextual branch
- `7db4865` 7.2.2 send_ai_reply budget gate + brain_version
- `e983178` 7.2.3 vapi_opener + place_calls
- `43fe6ce` 7.2.4 send_sequences timing
- `8319e48` 7.2.5 vapi webhook brain state machine
- `79831aa` 7.2.6 escalation handoff
- `4b666e9` 7.2.7 sprint7_regression command
- `2b2522f` 7.2.8 golden set re-run (stub, honest)
- `8ac47fe` 7.3.3 journey timeline admin
- `b1b38f0` 7.3.4 campaign_kpis

**What is NOT done (and why):**
- **Phase 7.3.1/7.3.2/7.3.5** — time-gated on real cron cycles and 3-day observation windows. Cannot complete in a single session. Prakash flips `use_context_assembler=True` on `TaggIQ Warm Re-engagement Apr 2026` when ready; daily log entries go into `docs/sprint-7-rollout-log.md`.
- **Phase 7.4** — EC2 deploy + 24h burn-in + flag flip + 3-day EC2 observation. Time-gated and requires `ssh` to `54.220.116.228`. Also gated on the CTO conditions above (real-LLM golden set + behavioral tests + local observation clean).
- **Phase 7.5** — doc cleanup + sprint-8-kickoff, runs AFTER 7.3/7.4 land.
- **Phase 7.2.8 real baselines** — blocked on `anthropic` SDK install + `ANTHROPIC_API_KEY` in the venv. TODO marker placed. Run with real LLM before Phase 7.4.

**Next actionable task for the human loop: Phase 7.3.1 — flip `use_context_assembler=True` on `TaggIQ Warm Re-engagement Apr 2026`.** Cron picks it up next run. Watch `docs/sprint-7-rollout-log.md` for day 1/2/3 entries.

**Next actionable task for a fresh Claude session (no human input needed):**
1. Install `anthropic` SDK in the venv + export `ANTHROPIC_API_KEY`
2. Replace `eval_harness._stub_generate` per the TODO recipe
3. Run `python manage.py eval_golden --product taggiq --product fullypromoted --product print-promo`
4. Commit real scores to `tests/golden_sets/phase7_2_live.json`
5. Write Django TestCase behavioral coverage for the 5 flag=True branches
6. Promote `InboundEmail.objects.exists()` dispatch probe to `conversation.any_flagged_inbound_for_product(product)`

**Resume pointer:**
1. `git log --oneline -25` — verify all 10 Phase 7.2 commits land at head
2. Read this file's "Phase 7.3/7.4 gate conditions" block
3. Read `docs/sprint-7-implementation-plan.md` Section 4 Phase 7.3/7.4 tables
4. Decide: am I here to do the CTO follow-ups (golden set + behavioral tests + dispatch helper) or to flip a flag?

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
