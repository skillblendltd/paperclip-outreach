# Sprint 8 Progress — Prospect Lifecycle State Machine + Call Pipeline Fix

**Started:** 2026-04-21
**Plan:** `docs/sprint-8-implementation-plan.md`
**Chief Orchestrator:** Update this file after every task completion.

---

## Current State

**Phase:** 3 — EC2 Deploy + Regression
**Status:** Phases 1A, 1B, 2 COMPLETE. Awaiting EC2 migration deploy + seed templates (Task 12).

---

## Task Board

| # | Task | Phase | Size | Status | Notes |
|---|------|-------|------|--------|-------|
| 1 | Fix call eligibility (allowlist in place_calls.py) | 1A | XS | DONE | Verified with dry-run |
| 2 | Fix dynamic_first_message (CallService.place_call signature) | 1A | S | DONE | first_message param added |
| 3 | Fix {{FNAME}} rendering in _get_first_message | 1A | XS | DONE | Renders name+there fallback |
| 4 | Wire channel_timing to static call path | 1A | XS | DONE | Verified: 1 prospect skipped in dry-run |
| 5 | Enrich vapi_opener with reply body + pain signals | 1A | S | DONE | Added last_reply, current_tools, pain_signals to prompt |
| 6 | Create ProspectEvent model + migration | 1B | S | DONE | migration 0021_prospect_event applied |
| 7 | Create campaigns/services/lifecycle.py | 1B | M | DONE | ALLOWED_TRANSITIONS map + side effects |
| 8 | Update place_calls.py callers to use lifecycle.transition | 1B | S | DONE | |
| 9 | Update vapi_webhook callers to use lifecycle.transition | 1B | S | DONE | |
| 10 | Update check_replies.py callers to use lifecycle.transition | 1B | M | DONE | |
| 11 | Add _queue_post_call_action to vapi_webhook | 2 | S | DONE | voicemail/demo_link/confirmation queuing |
| 12 | Seed post_call_voicemail + post_call_demo_link templates | 2 | S | PENDING | Need DB seeds per calling campaign |
| 13 | Create nudge_stale_leads management command | 2 | M | DONE | Uses ConversationState (not last_emailed_at) to avoid AI-reply false positives |
| 14 | Add nudge_stale_leads to cron schedule | 2 | XS | DONE | 30 11 * * 1-5, CRON_SEND_ARGS scoped |
| 15 | follow_up_later re-entry in nudge_stale_leads | 3 | S | DONE | Included in nudge_stale_leads command |
| 16 | Full regression dry-run | 3 | S | DONE | manage.py check + place_calls + nudge_stale_leads all pass |
| 17 | Deploy migration to EC2 | 3 | S | PENDING | Apply migration 0021 to EC2 |

---

## Progress Log

### 2026-04-21 — Sprint kicked off
- CTO plan written to docs/sprint-8-implementation-plan.md
- Progress tracker created
- Handed to chief-orchestrator for implementation

### 2026-04-21 — Phases 1A + 1B + 2 + 3 COMPLETE (local)
- All 5 P0 bugs fixed (eligibility allowlist, dynamic_first_message, FNAME, channel_timing, vapi_opener context)
- ProspectEvent model + migration 0021 applied
- lifecycle.py created — single gateway for all status changes
- All callers migrated: place_calls, vapi_webhook, check_replies
- _queue_post_call_action added to vapi_webhook
- nudge_stale_leads command created + tested with dry-run (correctly excluded 4 AI-replied prospects)
- follow_up_later re-entry included in nudge_stale_leads
- nudge_stale_leads added to cron schedule

## Pending: Task 12 (Template Seeds) + Task 17 (EC2 Deploy)

### Task 12: Email templates to seed per calling campaign
Three template_name values needed in EmailTemplate for each campaign with calling_enabled=True:
- `post_call_voicemail` — "Just left you a voicemail about [topic]"
- `post_call_demo_link` — "Great talking to you! Here's the demo link..."
- `demo_confirmation` — "Demo confirmed — see you [date]"

Run after Prakash confirms copy is right. These are silent no-ops until seeded.

### Task 17: EC2 Deploy
```bash
ssh -i ~/.ssh/paperclip-eu.pem ec2-user@54.220.116.228
cd ~/paperclip-outreach
git pull
source venv/bin/activate
python manage.py migrate
# Verify:
python manage.py check
python manage.py place_calls --dry-run
python manage.py nudge_stale_leads --dry-run
# Restart cron container to pick up new cron-entrypoint.sh:
docker compose restart cron
```

---

## Key File Locations

| File | Purpose |
|------|---------|
| `campaigns/management/commands/place_calls.py` | Task 1, 4, 8 |
| `campaigns/call_service.py` | Task 2, 3 |
| `campaigns/services/vapi_opener.py` | Task 5 |
| `campaigns/models.py` | Task 6 |
| `campaigns/services/lifecycle.py` | Task 7 (new file) |
| `campaigns/views.py` | Task 9, 11 |
| `campaigns/management/commands/check_replies.py` | Task 10 |
| `campaigns/management/commands/nudge_stale_leads.py` | Task 13 (new file) |
| `docker/cron-entrypoint.sh` | Task 14 |

---

## Verification Commands

Run after each phase completes:

```bash
# Phase 1A verification
cd /Users/pinani/Documents/paperclip-outreach
venv/bin/python manage.py place_calls --dry-run 2>&1 | head -50

# Phase 1B verification
venv/bin/python manage.py shell -c "
from campaigns.services.lifecycle import transition, ALLOWED_TRANSITIONS
print('Allowed transitions:')
for s, targets in ALLOWED_TRANSITIONS.items():
    print(f'  {s} -> {sorted(targets)}')
print('lifecycle.py OK')
"

# Phase 2 verification
venv/bin/python manage.py nudge_stale_leads --dry-run 2>&1

# Full regression
venv/bin/python manage.py send_sequences --dry-run --status
venv/bin/python manage.py place_calls --dry-run
venv/bin/python manage.py check_replies --dry-run --mailbox taggiq
```

---

## Rollback Notes

- Phase 1A: pure code changes, no migration. Rollback = git revert.
- Phase 1B: additive migration (new table). Rollback = `migrate campaigns 0XXX_prev`, delete lifecycle.py.
- Phase 2: no migration needed. Rollback = revert vapi_webhook change.
- Phase 3: no migration needed.
