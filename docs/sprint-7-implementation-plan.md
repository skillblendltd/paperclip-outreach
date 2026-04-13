# Sprint 7 — Sales Director Platform MVP

**Created:** 2026-04-13
**Status:** Planned, not started. Prakash approval pending on Phase 7.0 kickoff.
**Owner:** Prakash (decisions, brain authoring, flag flips) + Claude (implementation, eval)
**Related:**
- `docs/contextual-autonomous-marketing.md` — vision doc this sprint realizes
- `docs/sprint-6-implementation-plan.md` — prior sprint whose Phase 2A services this sprint consumes
- `docs/ai-reply-architecture.md` — org-agnostic reply pipeline this sprint builds on
- `docs/taggiq-warm-reengagement-plan.md` — first campaign to flip to the new path

## Objective

Ship a product-agnostic platform where each Product (and optionally each Campaign) carries its own "brain" — a JSON config of rules + a voice prompt template. Everything else is shared platform capability. Two brains running in production simultaneously on two deployment surfaces (TaggIQ on local, FP print-promo on EC2) is the acceptance test that proves the platform is real.

**Vision in one line:** Send → detect reply → classify → respond (email or call) → update prospect state → decide the next touch → repeat until booked or dead, with each product/campaign carrying its own decision brain.

## Non-negotiable constraints

1. **Zero impact on any existing campaign** while Sprint 7 is being built. Every new code path is gated by `Campaign.use_context_assembler` (reused from Sprint 6). `False` = old behavior, byte-identical.
2. **Two-host deployment coordination.** Local Docker (TaggIQ + FP Franchise + FP BNI) and EC2 `paperclip-outreach-eu` (print-promo) both run Postgres 16 with the same schema. Migration 0017 runs on both; brain rows are seeded per host.
3. **Golden set eval before Phase 2B wiring.** No merge into the live path without a green golden-set regression check. Prakash signs off on fixture quality.
4. **Rules engine, not LLM, decides next-action.** Deterministic, debuggable, free. LLM calls happen only at content generation (reply, call opener, transcript analysis). Sonnet 4.6 floor on all LLM jobs, configurable per-brain via `jobs` JSON.
5. **No new product-specific Python.** Any `if product.slug == 'taggiq':` conditional is a Sprint 7 review rejection. Differences live in brain JSON.

---

## 1. Current state (what Sprint 7 inherits)

| Area | State | Sprint 7 role |
|---|---|---|
| Migration head | `0016_sprint6_loom_hook_flag_budget` on both hosts | 0017 appends additively |
| `PromptTemplate` | Has `model`, `version`, persona metadata, `max_reply_words`. Lisa v5 row live on EC2. | No schema change. TaggIQ + FP Franchise get new rows seeded. |
| `AIUsageLog` | Has `prompt_version`. Missing `brain_version`. | One additive column in 0017. |
| `Organization` | Has `ai_budget_monthly_cents` + `ai_usage_current_month_cents` (0016). | Reused as-is by `ai_budget.py` gate. |
| `Campaign.use_context_assembler` | Flag exists (0016). Default `False`. | Reused as the single feature flag for the whole Sprint 7 path. |
| `conversation.py`, `context_assembler.py`, `channel_timing.py`, `ai_budget.py`, `cacheable_preamble.py` | Built in Sprint 6 Phase 2A as dark code. 38/38 tests pass. | Wired into live code in Phase 7.2 behind flag. |
| `handle_replies._build_execution_preamble` | Live on EC2 for Lisa v5 print-promo replies. | Untouched. Flag=False campaigns depend on it. |
| `send_ai_reply`, `send_sequences`, `place_calls` | Live on both hosts. No LLM decisioning. | Gain feature-flagged branches that call brain services. |
| TaggIQ Warm Re-engagement campaign | 15 prospects seeded, `sending_enabled=False`, `calling_enabled=True`, on local. | First campaign flipped to `use_context_assembler=True` in Phase 7.3. |
| Lisa v5 print-promo on EC2 | Live, handling FP Kingswood + Dublin Construction replies. | Second brain, flipped to new path in Phase 7.4 after local proves out. |

**The important framing:** Sprint 7 is 60% wiring existing pieces together, 30% writing the rules engine, 10% JSON authoring for the two brains. The only real net-new code is the rules engine itself (`rules_engine.py`, `next_action.py`, `brain.py`, `eval_harness.py`). Everything else is plumbing between things that already exist.

---

## 2. Architecture — final contract

### 2.1 New models (additive only, migration 0017)

**`ProductBrain`** — one row per `Product`:
```python
class ProductBrain(BaseModel):
    product               = OneToOneField(Product, related_name='brain')
    version               = IntegerField(default=1)
    is_active             = BooleanField(default=True)

    # Decision rules (rules-engine input, JSON)
    sequence_rules        = JSONField(default=dict)
    timing_rules          = JSONField(default=dict)
    terminal_states       = JSONField(default=list)
    escalation_rules      = JSONField(default=dict)
    success_signals       = JSONField(default=dict)
    call_eligibility      = JSONField(default=dict)

    # What to say on each touch (separate from how to sound)
    content_strategy      = JSONField(default=dict)

    # Per-job generation config (model, max_tokens, cache flag)
    jobs                  = JSONField(default=dict)

    # Voice + script links (not duplicated data)
    reply_prompt_template = ForeignKey(PromptTemplate, null=True, on_delete=PROTECT)
    call_script_default   = ForeignKey(CallScript, null=True, on_delete=SET_NULL)

    # Eval gate
    golden_set_path       = CharField(max_length=500, blank=True, default='')
    eval_threshold_pct    = IntegerField(default=95)

    class Meta:
        db_table = 'product_brain'
```

**`CampaignBrainOverride`** — sparse per-campaign overrides:
```python
class CampaignBrainOverride(BaseModel):
    campaign  = OneToOneField(Campaign, related_name='brain_override')
    overrides = JSONField(default=dict)  # sparse keys only

    class Meta:
        db_table = 'campaign_brain_override'
```

**`AIUsageLog.brain_version`** — nullable integer, default null. One ALTER.

No other schema changes. No data backfill. Existing rows untouched. Migration is idempotent and safe on both hosts.

### 2.2 New service layer

```
campaigns/services/
├── brain.py              NEW  load_brain(prospect) -> merged Brain dataclass
├── rules_engine.py       NEW  pure-python evaluator, ~300 lines, zero LLM
├── next_action.py        NEW  decide_next_action(prospect) -> NextAction
├── eval_harness.py       NEW  golden set runner, LLM-as-judge scoring
├── vapi_opener.py        NEW  pre-compute Vapi first_message from conversation
├── conversation.py       EXISTS, unchanged
├── context_assembler.py  EXISTS, unchanged
├── channel_timing.py     EXISTS, unchanged
├── ai_budget.py          EXISTS, unchanged
├── cacheable_preamble.py EXISTS, Phase 7.2 consumer
├── reply_audit.py        EXISTS, unchanged
├── safeguards.py         EXISTS, unchanged
├── send_orchestrator.py  EXISTS, unchanged
├── template_resolver.py  EXISTS, unchanged
└── eligibility.py        EXISTS, Phase 7.2 consumer
```

### 2.3 Brain JSON shapes (seeded in Phase 7.1.6 and 7.1.7)

Each JSON field in `ProductBrain` has a JSONSchema in `campaigns/brain_schemas/`. `ProductBrain.clean()` validates on save.

**`sequence_rules`** — maps prospect state to next sequence step:
```json
{
  "new":        {"next": "seq1", "after_hours": 0},
  "contacted":  {"next": "seq_next", "after_hours": 168},
  "interested": {"next": null, "handoff": "ai_reply"},
  "engaged":    {"next": null, "handoff": "ai_reply"}
}
```

**`timing_rules`** — cross-channel locks, per-channel caps:
```json
{
  "min_hours_since_inbound":  24,
  "min_hours_since_email":    48,
  "min_hours_since_call":     48,
  "max_emails_per_week":       3,
  "max_calls_per_prospect":    2
}
```

**`terminal_states`** — statuses where no further outreach happens:
```json
["demo_scheduled", "design_partner", "opted_out", "not_interested", "bounce"]
```

**`escalation_rules`** — when to ping Prakash:
```json
{
  "on_keyword":    ["pricing", "contract", "legal", "procurement"],
  "on_status":     ["interested"],
  "on_reply_count_gte": 3
}
```

**`success_signals`** — what counts as a win for KPI rollups:
```json
{
  "primary":   "demo_scheduled",
  "secondary": ["interested", "engaged"]
}
```

**`call_eligibility`** — when to graduate from email to call:
```json
{
  "min_emails_sent":   2,
  "require_open":      false,
  "require_phone":     true,
  "skip_if_replied":   true,
  "allowed_countries": ["US", "IE", "GB"]
}
```

**`content_strategy`** — what to say on each touch (separate from how to sound):
```json
{
  "per_sequence": {
    "seq1": "introduce supplier ordering with loom link",
    "seq2": "3-minute quote proof point",
    "seq3": "branded webstores + soft breakup",
    "seq4": "final soft close, what would it take"
  },
  "reply_goals": {
    "interested": "qualify budget + timeline, propose demo",
    "question":   "answer tactically, nudge to call"
  },
  "call_goals": {
    "warm_reengagement": "reference last email specifically, ask for 60 seconds"
  }
}
```

**`jobs`** — per-task model selection (Sonnet 4.6 floor):
```json
{
  "reply":              {"model": "claude-sonnet-4-6", "max_tokens": 500,  "cache": true},
  "call_opener":        {"model": "claude-sonnet-4-6", "max_tokens": 120},
  "classify":           {"model": "claude-sonnet-4-6", "method": "regex_first"},
  "transcript_insight": {"model": "claude-sonnet-4-6", "max_tokens": 1500}
}
```

### 2.4 Feature flag strategy

**Single flag: `Campaign.use_context_assembler`** (reused from Sprint 6, no new column).

| Flag | Code path |
|---|---|
| `False` (default, all existing campaigns) | Existing Sprint 5 v5 / Sprint 6 Phase 1A code. No brain, no context, no timing locks. **Byte-identical to pre-Sprint-7.** |
| `True` | New path: `next_action.decide()` gates, `context_assembler.build_context_window()` injects history, `cacheable_preamble.build()` drives Anthropic prompt caching, `ai_budget.check_budget_before_call()` gates spend, brain state machine updates prospect status. |

**Rollout:**
1. Phase 7.3.1 — flip on `TaggIQ Warm Re-engagement Apr 2026` (local, 15 prospects, zero risk)
2. Phase 7.3.5 — flip on a second local campaign after 3 clean days
3. Phase 7.4.4 — flip on one EC2 print-promo campaign after local has 3+ clean days

**Rollback** = flip bit back to `False`. Instant. No data loss. No code revert.

### 2.5 Explicitly out of scope

These are Phase 3 productization, not MVP:

- UI for editing brains (Django admin JSON editor is fine — Prakash is the only author)
- LLM-driven next-action decisioning (rules engine only for MVP)
- Attribution tokens in email footers
- TCPA state-specific call-time rules
- Per-org middleware isolation audit (convention still, not enforced)
- Kritno brain (product doesn't exist yet)
- Public API for design partners
- Usage-based billing
- Multi-language voice rules

Do not scope-creep these in. Add them after two brains are in production.

---

## 3. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Migration 0017 schema drift between local and EC2 | HIGH | Additive-only migration. Single file. Apply order: local first → verify `django_migrations` head → EC2. Postgres 16 on both. |
| 2 | Feature flag accidentally flipped on wrong campaign → untested code path ships | HIGH | `list_flagged_campaigns` management command prints all `use_context_assembler=True` campaigns. Run before every cron cycle during rollout. Flag change requires explicit Prakash approval. |
| 3 | Malformed brain JSON after manual admin edit → whole product stops replying | HIGH | `ProductBrain.clean()` validates against JSONSchema on save. `brain_doctor` management command lints every brain daily, alerts on drift. |
| 4 | Golden set not captured before Phase 7.2 wiring → no regression gate | HIGH | Phase 7.0 is a HARD BLOCKER on Phase 7.1 merges. No exceptions. |
| 5 | Prompt cache key collision across tenants → cross-tenant data leak | HIGH | Cache key MUST be `f"{org_id}:{product_id}:{prompt_template_version}:{brain_version}"`. Enforced in `cacheable_preamble.build()`. Unit test asserts the key format. |
| 6 | EC2 deploy lags local; brain changes on local not yet on EC2 cause divergent behavior across hosts | MED | Two-phase rollout: EC2 only after local has 3 days stable. `brain_version` visible in `AIUsageLog` for audit. No cross-host replication — each host owns its DB. |
| 7 | `next_action.decide()` returns `None` for too many prospects → silent pipeline stall | MED | Nightly metrics command prints `terminal / waiting / actionable / error` breakdown per campaign. Alert if actionable drops >50% week-over-week. |
| 8 | Rules engine disagrees with legacy `send_sequences` eligibility → duplicate or missed sends during transition | MED | Shadow mode (Phase 7.1.9): rules engine runs in parallel on all campaigns, logs decisions, does NOT act. Prakash reviews diffs before any flag flip. |
| 9 | Cost spike from context-injected replies on a product with long email threads | LOW | `ai_budget.check_budget_before_call()` gates each call, degrades to flat template when over. `AIUsageLog` weekly review. |
| 10 | Opus-as-judge cost on eval runs | LOW | Cap at 30 judgments/week; total <$5/month |
| 11 | Vapi `first_message` latency (Sonnet 4.6 at ~1.5s) in live call path | LOW | `vapi_opener.py` pre-computes at queue time, NOT in live call turn. Docs in `contextual-autonomous-marketing.md` lock this constraint. |
| 12 | `ai_budget.record_cost` race under concurrent writes | LOW | Already uses `F()` atomic increment per Sprint 6 Phase 2A. Verified in `sprint6_tests.py`. |

---

## 4. Sprint 7 task board

Five phases. Each task has size (S/M/L), owner, dependencies, acceptance criteria. Progress tracked in `docs/sprint-7-progress.md`, updated after every merge.

### Phase 7.0 — Eval foundation (2 days, HARD BLOCKER on 7.1)

| # | Task | Owner | Size | Depends | Acceptance |
|---|---|---|---|---|---|
| 7.0.1 | Capture golden set fixtures: 15 real inbound emails × 2 products (FP Lisa print-promo live, TaggIQ seeded) in `tests/golden_sets/{slug}.json` with ideal replies | Prakash + Claude | S | None | File exists, 30 pairs, Prakash-approved |
| 7.0.2 | Build `eval_harness.py`: runs `PromptTemplate` + brain + conversation context against golden set, invokes Opus 4.6 as judge, scores each pair on voice match / factual accuracy / length compliance / injection resistance, outputs pass% | Claude | M | 7.0.1 | `python manage.py eval_golden --product taggiq` returns summary dict + pass% |
| 7.0.3 | Lock baseline scores for both products, commit `tests/golden_sets/baseline.json` | Claude | S | 7.0.2 | File committed, both products >=90% |
| 7.0.4 | Runbook entry: how to run `eval_golden` before every merge that touches a brain, prompt template, or LLM-adjacent code | Claude | S | 7.0.3 | Runbook in this doc (Section 6) |

**Phase 7.0 gate:** cannot start Phase 7.1 without baseline scores captured and a reproducible eval command.

### Phase 7.1 — Data model + brain authoring (3 days, local only)

| # | Task | Owner | Size | Depends | Acceptance |
|---|---|---|---|---|---|
| 7.1.1 | Migration `0017_product_brain_and_overrides.py` — additive only: `ProductBrain`, `CampaignBrainOverride`, `AIUsageLog.brain_version`. Applied on local first. | Claude | M | 7.0.4 | Runs clean on local Postgres; `django_migrations` head advances to 0017; zero row changes on existing tables |
| 7.1.2 | `ProductBrain.clean()` — JSONSchema validation for each JSON field. Schemas in `campaigns/brain_schemas/`. Invalid save raises `ValidationError`. | Claude | M | 7.1.1 | Unit test: malformed brain raises; valid brain saves cleanly |
| 7.1.3 | `brain.py` service: `load_brain(prospect)` merges `ProductBrain` + `CampaignBrainOverride`, returns frozen `Brain` dataclass | Claude | S | 7.1.2 | Unit test: override keys win, base keys preserved, dataclass is immutable |
| 7.1.4 | `rules_engine.py`: pure-python evaluator. Interprets every JSON field on `ProductBrain`. Zero LLM calls. | Claude | L | 7.1.3 | 15+ unit tests covering every rule type; all pass |
| 7.1.5 | `next_action.py`: `decide_next_action(prospect) -> NextAction` — composes brain + `conversation.get_conversation_state()` + rules engine. Returns `(channel, when, reason)` or terminal. | Claude | M | 7.1.4 | Unit test + shadow-run on 50 real prospects, decisions logged not acted |
| 7.1.6 | Seed TaggIQ `ProductBrain` JSON from `CLAUDE.md` + warm re-engagement plan. Also seed TaggIQ reply `PromptTemplate` row (mirrors Lisa v5 pattern). | Claude (draft) + Prakash (review) | M | 7.1.5 | Brain row exists locally; `eval_golden --product taggiq` >= baseline |
| 7.1.7 | Seed FP Franchise `ProductBrain` JSON from UFG 7-step manual + existing Prakash voice notes. Also seed FP Franchise reply `PromptTemplate`. | Claude (draft) + Prakash (review) | M | 7.1.5 | Brain row exists locally; `eval_golden --product fp-franchise` >= baseline |
| 7.1.8 | `brain_doctor` management command: lints every brain nightly, alerts on schema drift | Claude | S | 7.1.2 | Cron entry added to local only (EC2 waits) |
| 7.1.9 | Shadow-mode metrics: `python manage.py next_action_preview --campaign X` prints what the rules engine would decide for each prospect without acting | Claude | S | 7.1.5 | Prakash reviews output for TaggIQ Warm Re-engagement + FP Franchise before Phase 7.2 |

**Phase 7.1 gate:** two brains seeded, golden set scores meet baseline, shadow mode output reviewed by Prakash. No code in the live execution path has been touched yet.

### Phase 7.2 — Wire executors through the brain (5 days, local only)

All work gated by `Campaign.use_context_assembler`. Existing campaigns untouched.

| # | Task | Owner | Size | Depends | Acceptance |
|---|---|---|---|---|---|
| 7.2.1 | `handle_replies` — feature flag branch. If `campaign.use_context_assembler=True`, invoke `cacheable_preamble.build()` with conversation context, read voice from brain's `reply_prompt_template`, record `brain_version` in `AIUsageLog`. Else fall through to existing `_build_execution_preamble` path. | Claude | M | 7.1.6, 7.1.7 | Regression: existing Lisa replies on flag=False byte-identical. Golden set on flag=True >= baseline. |
| 7.2.2 | `send_ai_reply` — wire `ai_budget.check_budget_before_call()` before invocation and `ai_budget.record_cost()` after. Degrade to flat template when over budget. Behavior on flag=False unchanged. | Claude | S | 7.2.1 | Unit test: budget-exceeded blocks and logs, does not raise |
| 7.2.3 | `vapi_opener.py` + `place_calls` feature flag branch. On flag=True, pre-compute Vapi `first_message` at queue time via `conversation.get_last_topic()` + Sonnet 4.6. Eligibility via `next_action.decide_next_action`. Timing via `channel_timing.can_place_call`. Flag=False uses static `CallScript` row. | Claude | M | 7.1.5 | Dry-run on Warm Re-engagement produces dynamic first_messages. Static path untouched. |
| 7.2.4 | `send_sequences` — feature flag branch. When flag=True, consult `channel_timing.can_send_email` before each send; skip with reason if blocked. Existing eligibility path unchanged on flag=False. | Claude | S | 7.1.4 | Dry-run: prospect who replied 2h ago is skipped with reason logged |
| 7.2.5 | Vapi webhook handler — on call end, route outcome through brain state machine (`rules_engine.apply_call_outcome`), update `Prospect.status` per brain rules, trigger next touch decision via `next_action`. | Claude | M | 7.2.3 | End-to-end test: mock webhook → prospect status changes per brain rules |
| 7.2.6 | Escalation handoff: when brain's `escalation_rules` fire, write note to `Prospect.notes` with `ESCALATION:` prefix and log structured entry. (Dedicated `EscalationEvent` table deferred to Sprint 8 unless Prakash requests.) | Claude | S | 7.1.4 | Test: hot-lead signal triggers escalation note on prospect |
| 7.2.7 | Full regression on local with flag=False everywhere → existing behavior byte-identical (diff EmailLog/CallLog counts before/after on a 1-hour dry window) | Claude | S | 7.2.1–7.2.6 | Zero diff |
| 7.2.8 | Golden set re-run on flag=True path → meets or beats baseline | Claude | S | 7.2.1 | Scores committed to `tests/golden_sets/phase7_2.json` |

**Phase 7.2 gate:** regression shows zero impact on flag=False campaigns AND golden set on flag=True meets baseline. Both required.

### Phase 7.3 — Local rollout (3 days)

| # | Task | Owner | Size | Depends | Acceptance |
|---|---|---|---|---|---|
| 7.3.1 | Flip `use_context_assembler=True` on `TaggIQ Warm Re-engagement Apr 2026` (local only). Requires Loom URL from Prakash to unblock `sending_enabled` too. | Prakash | S | 7.2.8 | Flag flipped, cron picks it up next run |
| 7.3.2 | Observe 3 days: daily log review, golden set spot-check, AI cost audit, reply quality review. Log entries in `docs/sprint-7-rollout-log.md`. | Prakash + Claude | M | 7.3.1 | Three daily entries |
| 7.3.3 | Journey timeline view: admin action on `Prospect` that renders conversation + decisions + calls + costs. Read-only. Works for any product. | Claude | M | 7.3.1 | Admin link works for any prospect on any campaign |
| 7.3.4 | `campaign_kpis` command: `python manage.py campaign_kpis --campaign X` prints replies, interested%, demos, cost/demo, escalations, cost per prospect touched. Pure read. | Claude | S | 7.3.1 | Command prints all metrics for any campaign |
| 7.3.5 | If Phase 7.3.2 all-green at day 3: flip flag on one more local campaign (Prakash picks smallest TaggIQ or FP Franchise cohort) | Prakash | S | 7.3.2 | Second campaign on new path |

**Phase 7.3 gate:** two local campaigns on new path for ≥3 days with no incidents; KPIs visible; golden set stable.

### Phase 7.4 — EC2 rollout (2 days)

| # | Task | Owner | Size | Depends | Acceptance |
|---|---|---|---|---|---|
| 7.4.1 | Deploy code to EC2: `git pull`, `docker compose build cron web`, `docker compose up -d`, migration 0017 applies on EC2 Postgres | DevOps (Claude-driven via SSH) | M | 7.3.5 | EC2 `django_migrations` head is 0017; existing FP Kingswood + Construction replies unchanged (flag=False on all EC2 campaigns at this point) |
| 7.4.2 | 24-hour EC2 burn-in with flag=False on all EC2 campaigns. Compare reply count / send count / cron run count / error log to pre-deploy baseline. | Claude | S | 7.4.1 | Zero diff in reply count, zero new errors |
| 7.4.3 | Seed FP print-promo `ProductBrain` JSON on EC2 (Lisa voice already in `PromptTemplate`, brain layer adds rules + content strategy on top). Reuse FP Franchise JSON as starting point with print-promo overrides. | Claude (draft) + Prakash (review) | M | 7.4.2 | Brain row exists on EC2; `brain_doctor` passes; `eval_golden` on EC2 >= baseline |
| 7.4.4 | Flip `use_context_assembler=True` on smallest EC2 campaign first (`FP Kingswood Business Area` or `Dublin Construction & Trades`) | Prakash | S | 7.4.3 | Flag flipped, cron picks it up |
| 7.4.5 | Observe 3 days on EC2 same as local. Full rollout to remaining EC2 campaign only after. | Prakash + Claude | M | 7.4.4 | Three daily rollout-log entries |

**Phase 7.4 gate:** platform running two brains across two deploy surfaces simultaneously. This IS the MVP acceptance test.

### Phase 7.5 — Cleanup + documentation (end of sprint)

| # | Task | Owner | Size | Depends | Acceptance |
|---|---|---|---|---|---|
| 7.5.1 | Update `docs/sprint-plan.md` with Sprint 7 completion row | Claude | S | 7.4.5 | Doc updated |
| 7.5.2 | Update `CLAUDE.md` v2 Status list — Sprint 7 DONE | Claude | S | 7.4.5 | Doc updated |
| 7.5.3 | Write Sprint 8 kick-off doc: remaining campaigns to migrate, Phase 3 productization scope | Claude | S | 7.4.5 | `docs/sprint-8-kickoff.md` exists |
| 7.5.4 | Deprecate `_build_execution_preamble` with comment and TODO. Do NOT delete — still used by flag=False campaigns until every campaign is migrated. | Claude | S | 7.4.5 | Comment added |

---

## 5. Implementation contract (rules for code review)

**Module boundaries — enforced at review:**
- `conversation.py` is the ONLY source of prospect history. No command reads `EmailLog` / `InboundEmail` / `CallLog` directly to make decisions.
- `next_action.decide_next_action()` is the ONLY source of "what to do next." No command hardcodes sequence-step-1 logic.
- `rules_engine.py` contains zero LLM calls. It reads brain data and prospect state, returns decisions. Deterministic.
- `brain.py` is the ONLY loader of brains. Never instantiate `ProductBrain` directly in command code.
- LLM calls happen in exactly two places: `send_ai_reply` (replies) and `vapi_opener.py` (call openers). Nowhere else.

**Patterns required:**
- Every AI call writes `AIUsageLog` with full tuple: `organization + product + campaign + prospect + prompt_version + brain_version + cost + latency + success`.
- Every feature-flagged branch has both paths covered by a regression test.
- Every new JSON field on `ProductBrain` has a JSONSchema in `campaigns/brain_schemas/` and a validation test.

**Anti-patterns — REJECT at review:**
- Adding a column to `Campaign` or `Prospect` in Sprint 7. Brain config lives in `ProductBrain`/`CampaignBrainOverride`.
- `if product.slug == 'taggiq': ...` conditionals. Product-specific behavior lives in brain JSON.
- LLM calls inside `rules_engine.py` or `next_action.py`.
- Touching `handle_replies._build_execution_preamble` — deprecated but still live on flag=False campaigns.
- Breaking changes to `send_sequences` / `place_calls` / `handle_replies` on the flag=False path. **Byte-sacred during Sprint 7.**

**File conventions:**
- Migrations: `campaigns/migrations/0017_product_brain_and_overrides.py` (single migration file for all Phase 7.1 schema)
- Brain JSON schemas: `campaigns/brain_schemas/{field_name}.json`
- Golden sets: `tests/golden_sets/{product_slug}.json` + `baseline.json` + `phase7_2.json`
- Brain seed commands: `campaigns/management/commands/seed_brain_{product_slug}.py` (idempotent, re-runnable)

---

## 6. Deployment coordination

### 6.1 Host roster

| Host | Role | Postgres | Cron partition | Access |
|---|---|---|---|---|
| Local Docker | Primary dev, TaggIQ + FP Franchise rollout | `outreach_db` container | `--exclude-product print-promo` | `docker exec -it outreach_cron bash` |
| EC2 `paperclip-outreach-eu` | Lisa print-promo production | `outreach_db` container | `--product print-promo` | `ssh -i ~/.ssh/paperclip-eu.pem ec2-user@54.220.116.228` |

Both hosts: Postgres 16 on Alpine. Both: `django_migrations` head `0016` today. Both: same Django code, same `docker compose` setup.

### 6.2 Migration apply order

```
Phase 7.1.1  → local only (migration 0017)
Phase 7.2    → local only (feature-flagged code, all campaigns flag=False)
Phase 7.3    → local flag flips (TaggIQ Warm Re-engagement first)
Phase 7.4.1  → EC2 code deploy + migration 0017
Phase 7.4.2  → EC2 burn-in 24h (all campaigns flag=False)
Phase 7.4.4  → EC2 flag flip (one print-promo campaign)
```

**Rollback:** flip flag back to False on the affected campaign. Instant.

### 6.3 Brain row authoring workflow

1. Edit brain JSON locally via Django admin or `seed_brain_{slug}` management command
2. Run `eval_golden --product X` locally → must pass
3. Run `brain_doctor` locally → must pass
4. If the product also exists on EC2 (i.e., `print-promo`), SSH to EC2 and re-run the same seed command. **No automated replication.** Manual step by design — trades convenience for safety.
5. Verify `AIUsageLog` on EC2 next cron cycle shows incremented `brain_version`

### 6.4 What flows between hosts

| Thing | Flows? | How |
|---|---|---|
| Django code | YES | `git pull` on each host |
| Migrations | YES | Same file, applied per host via `manage.py migrate` |
| Docker image (cron/web) | YES | `docker compose build` on each host |
| `.env` secrets | NO | Host-specific |
| Postgres data | NO | Each host owns its data |
| `ProductBrain` rows | NO | Seeded per host |
| Nightly backups | Separate | Local → Google Drive; EC2 → Google Drive (different folders) |

---

## 7. Eval runbook (Phase 7.0 deliverable)

### 7.1 Running the golden set

```bash
# Score current reply path against golden set for a product
python manage.py eval_golden --product taggiq
python manage.py eval_golden --product fp-franchise
python manage.py eval_golden --product print-promo

# Compare flag=False vs flag=True on same campaign
python manage.py eval_golden --campaign "TaggIQ Warm Re-engagement Apr 2026" --compare

# Verbose mode: show each pair's judge verdict
python manage.py eval_golden --product taggiq --verbose
```

### 7.2 When to run eval

- Before every merge that touches `handle_replies`, `send_ai_reply`, `cacheable_preamble`, `context_assembler`, any brain JSON, or any `PromptTemplate` row
- Before every flag flip
- Weekly during rollout (7.3 and 7.4) — track drift

### 7.3 Judge model

Opus 4.6 as judge. Scores each pair on 4 axes (0–5 each, weighted):
- **Voice match** (40%) — does the reply sound like the persona defined in `PromptTemplate`
- **Factual accuracy** (30%) — does the reply handle the question without hallucinating
- **Length compliance** (15%) — under `max_reply_words`, no em dashes, no corporate fluff
- **Injection resistance** (15%) — does the reply ignore any prompt-injection in the inbound

Pass threshold: total >= 90% against golden set. Hard floor: no axis below 3/5 on any pair.

### 7.4 Cost envelope

- 30 pairs × 2 products = 60 judgments per weekly run
- Opus 4.6 ≈ $0.08 per judgment
- **Weekly eval cost: ≈ $5**
- Acceptable. Budget cap in `ai_budget.py` applies.

---

## 8. Progress tracking

Live state: `docs/sprint-7-progress.md`, updated after every merge using this template:

```
## Progress Update — YYYY-MM-DD
**Phase:** 7.X
**Active Task:** 7.X.Y — description
**Status:** In Progress / Merged / Blocked

**Completed since last update:**
- 7.X.Y — description (commit hash)

**Golden set scores:**
- taggiq:       XX% (baseline YY%)
- fp-franchise: XX% (baseline YY%)
- print-promo:  XX% (baseline YY%)

**Flag state:**
- Local: [campaigns with use_context_assembler=True]
- EC2:   [campaigns with use_context_assembler=True]

**Issues / Risks:**
- ...

**Next:**
- 7.X.Z — description
```

---

## 9. Open questions for Prakash (resolve before Phase 7.0)

1. **Golden set collaboration window** — need ~90 minutes of Prakash's time to review 30 real inbound emails and tag ideal replies. When?
2. **Ifrah US test call** — still happen on the current path (Sprint 6 static script) as throwaway Vapi/Telnyx infra validation, separate from Sprint 7? I recommend yes — de-risks dialing independently.
3. **Brain authoring split** — Claude drafts both brains from docs + CLAUDE.md, Prakash reviews both? Or Prakash writes FP Franchise content (UFG manual is his domain) and Claude drafts TaggIQ?
4. **Loom URL for Warm Re-engagement** — still blocking Phase 1B launch. Does this block Phase 7.3 flag flip or is the flag flip decoupled (i.e., we flip flag but `sending_enabled` stays False until Loom lands)?
5. **EC2 rollout timing** — is the 3-day local observation window acceptable, or does Prakash want longer before touching Lisa's print-promo production pipeline?

---

## 10. Acceptance test for Sprint 7 MVP

**Two brains running in production simultaneously on two hosts, with zero shared product-specific Python code.**

Specifically:
- [ ] `ProductBrain` row exists for TaggIQ on local, scores >= baseline on golden set
- [ ] `ProductBrain` row exists for FP Franchise on local, scores >= baseline on golden set
- [ ] `ProductBrain` row exists for FP print-promo on EC2, scores >= baseline on golden set
- [ ] At least one local campaign has `use_context_assembler=True` and has been running for 3 days without incident
- [ ] At least one EC2 campaign has `use_context_assembler=True` and has been running for 3 days without incident
- [ ] `grep -rn "if product.slug" campaigns/ | grep -v tests/` returns zero results
- [ ] `grep -rn "_build_execution_preamble" campaigns/` shows only the deprecated function definition, not new callers
- [ ] Golden set regression check is part of the pre-merge runbook and has been run at least 5 times
- [ ] `sprint-7-progress.md` shows full phase completion

If all checkboxes tick, Sprint 7 is done. If adding a hypothetical Kritno brain next sprint requires any Python change outside a new `ProductBrain` row + `PromptTemplate` row, the contract failed.

---

## 11. Resume instructions for next session

1. Read this file AND `docs/contextual-autonomous-marketing.md` (vision)
2. Read `docs/sprint-7-progress.md` for current state — which task is active
3. `git log --oneline -15` to see recent commits
4. Find the first unchecked task in the relevant phase table above
5. Execute it, update `sprint-7-progress.md`, commit, move to the next
6. Never break the Conversation service firewall rule (only `conversation.py` reads history)
7. Never add a product-specific Python conditional
8. Never touch `_build_execution_preamble` — it's the flag=False fallback
