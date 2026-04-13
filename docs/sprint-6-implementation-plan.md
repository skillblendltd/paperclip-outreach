# Sprint 6 Implementation Plan — Contextual Autonomous Marketing

**Created:** 2026-04-13
**Status:** In execution (Phase 1A + Phase 2A in parallel, Phase 1B/2B gated)
**CTO approval:** Given, with AI architect additions folded in
**Related docs:** `contextual-autonomous-marketing.md` (vision) + `taggiq-warm-reengagement-plan.md` (Phase 1 content)

## Scope of this doc

This is the **execution playbook**. It defines exactly what gets built, in what order, with what acceptance criteria, and what must NOT be touched. The chief-orchestrator executes from this doc. If anything disagrees with the vision or plan docs, THIS doc wins for execution decisions.

## Non-negotiables (enforced on every commit)

| Rule | Why |
|---|---|
| **No impact on Lisa v5 reply pipeline on EC2** | It's processing real customer replies right now |
| **No impact on existing laptop sequences** (TaggIQ BNI × 11, FP Franchise, FP Dublin B2B, etc.) | They send Mon-Fri 11:00 Dublin, mid-send disruption loses prospects |
| **Phase 2A is 100% additive greenfield** — zero modifications to `handle_replies.py`, `send_ai_reply.py`, `place_calls.py`, `send_sequences.py`, or `template_resolver.py` core logic | Any live-code change risks regression |
| **Feature flag `Campaign.use_context_assembler` defaults False** | Dark shipping - Phase 2 code exists but is unreachable from existing campaigns |
| **Migration adds only nullable / default-valued fields** | Zero data movement, zero existing-row impact |
| **Unit tests run against real existing prospects (Julie, Brian, Paul)** — not synthetic fixtures | AI architect principle: start with the data |
| **Rule-based assembler only — NO LLM calls inside `context_assembler.py`** | Determinism, cost, latency, debuggability |
| **Prompt caching markers designed in from Phase 2A** | 80-90% future cost saving, free to add now |
| **Per-org AI budget ceiling enforced on every new AI call path** | Fail-safe against runaway loops |
| **Prompt injection hardening via `<untrusted>` tags when inbound content enters prompts** | Appears the moment context assembly goes live — design in now |

## Phased execution

```
Phase 1A (execute now, ~45 min)  Phase 2A (execute now, ~2-3 hr)
  campaign build, dark code         greenfield services, dark code
          │                                   │
          └──────────────┬────────────────────┘
                         │
                   Commit + push
                         │
                         ▼
                   [HANDOFF POINT]
                         │
               Prakash records Loom
                         │
                         ▼
         Phase 1B (Tuesday launch, ~10 min)
              flat-template send goes live
                         │
                         ▼
         7 days of real traffic + reply data
                         │
                         ▼
      Phase 2B (wire context assembler, ~30 min)
         feature flag flipped on campaign,
         live code minimally modified
                         │
                         ▼
                 A/B measure for 7 days
                         │
                         ▼
         Phase 2C (generalize if it wins)
            apply to Lisa, FP, future campaigns
```

## Phase 1A — Campaign build (pure additive, no live code impact)

| # | Task | Size | Files touched | Acceptance |
|---|---|---|---|---|
| 1A.1 | Add 5 fields via single migration `0016`: `Campaign.loom_url`, `Campaign.use_context_assembler`, `Prospect.personal_hook`, `Organization.ai_budget_usd_monthly`, `Organization.ai_usage_current_month_cents` | S | `campaigns/models.py`, new migration file | `manage.py check` passes. All existing rows get defaults. |
| 1A.2 | `template_resolver.py`: add `LOOM_URL` and `PERSONAL_HOOK` to the variables dict | XS | `campaigns/services/template_resolver.py` | Existing templates still render. New variables available to new templates. |
| 1A.3 | Create `Warm Re-engagement Apr 2026` Campaign row with full config (from/reply/send window/cap/calling_enabled/feature flag False) | S | seeding script in `transfer/` | New campaign exists, `sending_enabled=False` until Loom arrives |
| 1A.4 | Create 4 EmailTemplate rows (Seq 1 supplier ordering / Seq 2 3-min quote / Seq 3 webstores+breakup / Seq 4 soft close) with `{{LOOM_URL}}` + `{{PERSONAL_HOOK}}` placeholders | M | seeding script | Templates render correctly when run through `template_resolver` |
| 1A.5 | Create CallScript row — US-only, Ifrah target, static first_message (Vapi dynamic generation is Phase 2B) | XS | seeding script | CallScript tied to new campaign, `is_active=True` |
| 1A.6 | Re-assign 15 approved prospects to new campaign; preserve original `campaign_id` in `notes` field; set per-prospect `personal_hook` | M | seeding script | 15 prospects have `campaign_id` = new campaign. Notes contain `[migrated from <old campaign>]`. |
| 1A.7 | Update Nick Militello status: `engaged → not_interested` with note "strategic contact (Tekweld network), not a buyer - exclude from all TaggIQ sequences" | XS | one-off shell | Nick's status reads `not_interested`, note appended |
| 1A.8 | Dry-run `send_sequences --campaign "Warm Re-engagement" --dry-run --status` — verify all 15 render | XS | none | Dry-run prints 15 prospects, all templates render, no exceptions |
| 1A.9 | Git commit + push | XS | `git` | `origin/main` has Phase 1A commit |

**Expected state after Phase 1A:**
- New Campaign exists in DB, `sending_enabled=False`, `loom_url=''` (placeholder)
- 15 prospects migrated with personal hooks
- Templates drafted with Loom placeholder
- **Nothing sends yet. Nothing changes for existing campaigns.**

## Phase 2A — Greenfield services (pure additive, dark code)

**File layout:** All new files. Zero edits to existing `handle_replies.py`, `send_ai_reply.py`, `place_calls.py`, `send_sequences.py`, or `template_resolver.py` core logic.

| # | Task | Size | Files created | Acceptance |
|---|---|---|---|---|
| 2A.1 | `campaigns/services/conversation.py` — `get_prospect_timeline(prospect, days=30)` returns chronological event list; `get_last_topic(prospect)` returns 1-line summary; `get_conversation_state(prospect)` returns structured state dict | M | new file | Test against Julie Keene — returns her demo notes, Apr 8 trial signup, Apr 13 activation nudge in chronological order |
| 2A.2 | `campaigns/services/context_assembler.py` — `build_context_window(prospect, max_tokens=2000, signature_name='')` returns a formatted string with `<untrusted>` tags wrapping all inbound content, rule-based truncation, no LLM calls | M | new file | Test with 3 prospects of varying history depths. Budget enforcement verified. Injection wrapping verified. |
| 2A.3 | `campaigns/services/channel_timing.py` — `can_send_email(prospect)`, `can_place_call(prospect)` with configurable gap windows reading from Campaign | S | new file | Pure read queries. Test: a prospect with `reply_sent_at` 1h ago → `can_place_call=False`. |
| 2A.4 | `campaigns/services/ai_budget.py` — `check_budget_before_call(org)` returns `(allowed, reason)`, `record_cost(org, cents)` increments `ai_usage_current_month_cents`, monthly reset logic | S | new file | Test: org at 100% budget → `allowed=False`. Reset on month boundary. |
| 2A.5 | `campaigns/services/cacheable_preamble.py` — NEW alternative preamble builder that emits the same content as `handle_replies._build_execution_preamble` but with Anthropic `cache_control` markers on the static prefix. This is the FUTURE Phase 2B entry point. Live code doesn't import it yet. | M | new file | Output matches `handle_replies._build_execution_preamble` structurally for same inputs. Cache markers present. |
| 2A.6 | Shadow eval command: `python manage.py eval_replies --product taggiq --sample 5` — generates BOTH flat and assembled drafts for N real prospects, prints side-by-side for human scoring. Does NOT send. | M | new file `campaigns/management/commands/eval_replies.py` | Running it produces readable paired output for 5 prospects. Zero writes to DB. |
| 2A.7 | Unit tests for 2A.1-2A.4 against real prospects (Julie Keene, Brian at C&S Roofing, Paul Rivers, Jere Putkisaari, Nick Militello) | M | new `tests/test_phase2a_services.py` | `python manage.py test campaigns.tests.test_phase2a_services` passes |
| 2A.8 | Regression test: verify Lisa v5 reply flow unchanged. Run `handle_replies --product print-promo --dry-run` and compare output to baseline | S | verification run | No diff from pre-Phase-2A behavior |
| 2A.9 | Regression test: verify existing laptop sequences unchanged. Run `send_sequences --status` on laptop and confirm 16 existing campaigns render same counts | S | verification run | No diff from pre-Phase-2A behavior |
| 2A.10 | Update `docs/contextual-autonomous-marketing.md` with Phase 2A service contracts (signatures, return types, usage examples, constraints) | S | doc edit | Service layer documented, next-session continuation is unambiguous |
| 2A.11 | Git commit + push | XS | `git` | `origin/main` has Phase 2A commit |

## Phase 1B — Campaign launch (GATED on Loom URL)

**DO NOT execute during this run.** This is a ~10 min task when Prakash provides the Loom URL.

| # | Task | Size |
|---|---|---|
| 1B.1 | Update `Campaign.loom_url` on the new campaign with the real URL | XS |
| 1B.2 | Run final dry-run to verify all 4 emails render with Loom URL substituted | XS |
| 1B.3 | Set `sending_enabled=True` on the campaign | XS |
| 1B.4 | Wait for next 09:00 Dublin Tuesday tick, watch `/tmp/campaigns_daily.log` | — |
| 1B.5 | Vapi call to Ifrah fires Thursday per cron schedule | — |

## Phase 2B — Wire context assembler (GATED on 7 days of Phase 1 real data)

**DO NOT execute during this run.** This is the minimum-diff integration AFTER we have real reply data to validate against.

| # | Task | Size | Files touched |
|---|---|---|---|
| 2B.1 | Run `eval_replies --product taggiq --sample 10` on real prospects — compare flat vs assembled | S | — |
| 2B.2 | Prakash human-scores 5-10 pairs (10 min) | — | — |
| 2B.3 | If assembled wins, modify `handle_replies._build_execution_preamble` to check `Campaign.use_context_assembler` and call `cacheable_preamble.build()` when True. ~10 line diff. | S | `handle_replies.py` |
| 2B.4 | Modify `place_calls.py` to pre-compute Vapi `first_message` at queue time (not call time) using `conversation.get_last_topic()`. | S | `place_calls.py` |
| 2B.5 | Set `Campaign.use_context_assembler=True` on the warm re-engagement campaign only | XS | — |
| 2B.6 | Monitor for 3 days — reply rate, audit warnings, cost | — | — |

## Safety: what must NOT change during Phase 1A + 2A execution

| File | Restriction |
|---|---|
| `handle_replies.py` | No modifications. Phase 2A services are not imported here. |
| `send_ai_reply.py` | No modifications. Pre-send detectors stay as-is. |
| `send_sequences.py` | No modifications. Existing cron runs identical. |
| `place_calls.py` | No modifications. Static Vapi first_message stays. |
| `template_resolver.py` | Only ADD `LOOM_URL` + `PERSONAL_HOOK` to the variables dict (Phase 1A.2). No other changes. |
| Lisa v5 PromptTemplate row in DB | Untouched. Print-promo reply flow stays on v5. |
| Existing laptop EmailTemplate rows (TaggIQ BNI, FP, etc.) | Untouched. |
| Existing CallScript rows (Lisa Kingswood, Construction) | Untouched. |
| Existing MailboxConfig rows | Untouched. |
| Cron schedule (`docker/cron-entrypoint.sh`) | Untouched. |
| `CRON_SEND_ARGS` / `CRON_REPLY_ARGS` env vars on laptop + EC2 | Untouched (partition stays: print-promo on EC2, rest on laptop). |

## Quality gates (must pass before commit)

After Phase 1A:
- [ ] `python manage.py check` passes
- [ ] `python manage.py migrate` succeeds
- [ ] `python manage.py send_sequences --dry-run --status` shows 16 campaigns EXCLUDING `print-promo` (same as before) PLUS new Warm Re-engagement campaign with `sending_enabled=False`
- [ ] Existing Lisa v5 reply test via `handle_replies --product print-promo` on EC2 returns same state as before
- [ ] Nothing new in `/tmp/campaigns_daily.log` (existing cron not disrupted)
- [ ] All 15 prospects in new campaign have non-empty `personal_hook`
- [ ] Nick Militello has `status=not_interested`

After Phase 2A:
- [ ] All Phase 1A gates still pass
- [ ] `python manage.py test campaigns.tests.test_phase2a_services` passes
- [ ] `python manage.py eval_replies --product taggiq --sample 3` prints 3 paired drafts without writing to DB
- [ ] `handle_replies --product print-promo` still behaves identically (Lisa v5 regression test)
- [ ] `send_sequences --status` shows identical campaign counts and eligible counts to pre-Phase-2A
- [ ] Zero imports of Phase 2A services from `handle_replies.py`, `send_ai_reply.py`, `send_sequences.py`, `place_calls.py` (grep verification)

## Rollback strategy

| Scenario | Rollback |
|---|---|
| Phase 1A migration breaks on EC2 | `manage.py migrate campaigns 0015` (revert to Sprint 5 v5 state) |
| Phase 1A seeding creates bad campaign rows | Delete the new campaign row (cascade deletes templates + callscript). Prospect re-assignments reversible via preserved `[migrated from X]` notes. |
| Phase 2A services have a bug | Zero impact — they're unreachable from live code. Fix in-place, commit again. |
| Phase 2B wiring regresses Lisa replies | Revert `handle_replies.py` commit. Feature flag stays False. |

## Out of scope for this run

- Phase 1B launch (waits for Loom)
- Phase 2B wiring (waits for Phase 1 real data)
- Phase 3 productization (weeks away)
- TaggIQ + FP Franchise reply DB PromptTemplates (separate sprint)

## Commit structure (CTO requires this order)

1. `feat(sprint6): migration 0016 (loom_url + personal_hook + feature flag + budget fields)` — Phase 1A.1 only
2. `feat(sprint6): template_resolver + Warm Re-engagement campaign seed` — Phase 1A.2-1A.7
3. `feat(sprint6-phase2a): conversation + context_assembler + channel_timing + ai_budget services` — Phase 2A.1-2A.4
4. `feat(sprint6-phase2a): cacheable_preamble + eval_replies command` — Phase 2A.5-2A.6
5. `test(sprint6-phase2a): service tests against real prospects + regression checks` — Phase 2A.7-2A.9
6. `docs(sprint6-phase2a): service contracts documented` — Phase 2A.10

Six commits, each self-contained, reviewable, revertable.

## Success criteria for this run

Run is COMPLETE when:
- All Phase 1A quality gates pass
- All Phase 2A quality gates pass
- 6 commits on origin/main
- Final status report shows: "ready for Phase 1B launch pending Loom URL. Phase 2A dark code shipped, awaiting Phase 1 real data."

Run is FAILED if:
- Any existing campaign behavior changes
- Lisa v5 reply flow on EC2 regresses
- Any live code file has unintended modifications
- Quality gates don't pass

## Handoff to chief-orchestrator

The chief-orchestrator reads this doc and executes in strict order:

1. Phase 1A tasks 1A.1 through 1A.9
2. Commit 1A
3. Phase 2A tasks 2A.1 through 2A.11
4. Commits 2A (split per the commit structure above)
5. Final report
