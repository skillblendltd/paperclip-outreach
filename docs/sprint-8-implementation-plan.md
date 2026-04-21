# Sprint 8 — Prospect Lifecycle State Machine + Call Pipeline Fix

**CTO Sign-off:** Prakash Inani / Claude CTO Architect
**Date:** 2026-04-21
**Status:** APPROVED FOR IMPLEMENTATION

---

## Problem Statement

The outbound pipeline has three independent cron jobs (`send_sequences`, `place_calls`, `handle_replies`) with no coordination layer. Prospect status transitions happen in 6+ different files with no enforcement, no audit trail, and no attached side effects. The result:

1. Cold prospects (`contacted`) are being called — wrong channel for the signal
2. Personalized Vapi openers are computed but never actually used (bug in CallService)
3. `{{FNAME}}` template vars aren't rendered before going to Vapi
4. No cross-channel timing guard on the static call path
5. After a call ends, no automated next action fires (voicemail → no email; interested call → no demo link sent)
6. `interested` prospects sit indefinitely with no nudge if they don't book
7. `follow_up_later` status is a dead end — nothing re-triggers it
8. After 5 emails + no reply, prospects stay `contacted` forever

**Root cause:** Every fix so far has been additive to independent subsystems. The system needs a Transition Gateway — a single function that all status changes go through, with side effects declared centrally.

---

## Architecture Decision

### What We're Building

A lightweight prospect lifecycle module (`campaigns/services/lifecycle.py`) that:
- Defines allowed state transitions as a map
- Is the ONLY way to change `prospect.status`
- Fires side effects on entry to new states
- Logs every transition to `ProspectEvent` for audit

**What we're NOT building:**
- An FSM library (`django-fsm`, `python-statemachine`) — overkill for 10 states
- A workflow engine — no BPMN, no visual designer
- A message queue / Celery — EmailQueue already handles scheduling

### Module Boundaries

```
campaigns/services/lifecycle.py     — transition gateway + side effects
campaigns/models.py                  — ProspectEvent model (new)
campaigns/migrations/XXXX_...py      — ProspectEvent migration
campaigns/management/commands/       — callers updated to use lifecycle.transition()
campaigns/views.py                   — vapi_webhook updated to use lifecycle.transition()
campaigns/management/commands/check_replies.py  — updated
```

**Rule:** No file outside `lifecycle.py` may write `prospect.status = X` directly.
Exception: Django admin (manual override by Prakash only, acceptable).

---

## Data Model

### New: ProspectEvent

```python
class ProspectEvent(BaseModel):
    """Audit trail for every prospect status transition."""
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='events')
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    reason = models.CharField(max_length=200)         # e.g. 'reply:interested', 'call:voicemail'
    triggered_by = models.CharField(max_length=50)   # 'handle_replies', 'vapi_webhook', 'place_calls', 'admin'
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['prospect', '-created_at']),
        ]
```

No migration-safe concerns — purely additive new table.

---

## lifecycle.py Design

```python
# campaigns/services/lifecycle.py

ALLOWED_TRANSITIONS = {
    'new':             {'contacted'},
    'contacted':       {'interested', 'engaged', 'not_interested', 'opted_out', 'follow_up_later'},
    'engaged':         {'interested', 'not_interested', 'opted_out', 'demo_scheduled', 'follow_up_later', 'engaged'},
    'interested':      {'demo_scheduled', 'not_interested', 'opted_out', 'follow_up_later', 'engaged'},
    'demo_scheduled':  {'customer', 'design_partner', 'not_interested', 'follow_up_later'},
    'follow_up_later': {'contacted', 'interested', 'not_interested', 'opted_out'},
    'design_partner':  {'customer', 'demo_scheduled'},
    # Terminal: opted_out, not_interested, customer — no outbound transitions
}

def transition(prospect, new_status, reason, triggered_by='system'):
    """The ONLY way to change prospect.status outside Django admin.
    
    Validates transition is allowed, saves, logs ProspectEvent,
    and fires side effects for the new state.
    
    Returns the ProspectEvent created.
    Raises ValueError for illegal transitions (caller should catch + log).
    """
    current = prospect.status or 'new'
    allowed = ALLOWED_TRANSITIONS.get(current, set())

    if new_status == current:
        return None  # No-op, not an error

    if new_status not in allowed:
        raise ValueError(
            f'Illegal transition: {current} -> {new_status} '
            f'(prospect={prospect.id}, reason={reason})'
        )

    prospect.status = new_status
    prospect.save(update_fields=['status', 'updated_at'])

    from campaigns.models import ProspectEvent
    event = ProspectEvent.objects.create(
        prospect=prospect,
        from_status=current,
        to_status=new_status,
        reason=reason,
        triggered_by=triggered_by,
    )

    _fire_side_effects(prospect, from_status=current, to_status=new_status)
    return event


def _fire_side_effects(prospect, from_status, to_status):
    """Declarative side effects attached to state entry.
    
    Each block is independent and wrapped in try/except — a failing
    side effect must NEVER roll back the transition itself.
    """
    try:
        _side_effects_map(prospect, from_status, to_status)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(
            'lifecycle side_effect failed prospect=%s %s->%s: %s',
            prospect.id, from_status, to_status, exc
        )


def _side_effects_map(prospect, from_status, to_status):
    import logging
    logger = logging.getLogger(__name__)
    
    if to_status == 'demo_scheduled':
        # Queue demo confirmation email (via EmailQueue, 30-min delay)
        _queue_email(prospect, template='demo_confirmation', delay_hours=0.5,
                     triggered_by='lifecycle:demo_scheduled')
    
    elif to_status == 'follow_up_later':
        # Set re-entry date 30 days out
        from django.utils import timezone
        from datetime import timedelta
        if not prospect.follow_up_after or prospect.follow_up_after < timezone.now():
            prospect.follow_up_after = timezone.now() + timedelta(days=30)
            prospect.save(update_fields=['follow_up_after', 'updated_at'])
    
    elif to_status == 'opted_out':
        # Ensure send_enabled=False and product-scoped suppression
        if prospect.send_enabled:
            prospect.send_enabled = False
            prospect.save(update_fields=['send_enabled', 'updated_at'])
        _add_suppression(prospect, reason='lifecycle:opted_out')
    
    elif to_status == 'not_interested':
        if prospect.send_enabled:
            prospect.send_enabled = False
            prospect.save(update_fields=['send_enabled', 'updated_at'])


def _queue_email(prospect, template, delay_hours=0, triggered_by='lifecycle'):
    """Queue an email via EmailQueue for deferred send."""
    from django.utils import timezone
    from datetime import timedelta
    from campaigns.models import EmailQueue, EmailTemplate
    
    campaign = prospect.campaign
    if not campaign:
        return
    
    tmpl = EmailTemplate.objects.filter(
        campaign=campaign,
        template_name=template,
        is_active=True,
    ).first()
    if not tmpl:
        return  # No template configured, skip silently
    
    send_after = timezone.now() + timedelta(hours=delay_hours)
    EmailQueue.objects.get_or_create(
        prospect=prospect,
        campaign=campaign,
        template=tmpl,
        status='pending',
        defaults={'send_after': send_after, 'triggered_by': triggered_by},
    )


def _add_suppression(prospect, reason='lifecycle'):
    from campaigns.models import Suppression
    campaign = prospect.campaign
    if not campaign or not campaign.product_ref:
        return
    Suppression.objects.get_or_create(
        product=campaign.product_ref,
        email=prospect.email.lower() if prospect.email else '',
        defaults={'reason': reason},
    )
```

---

## Bug Fixes (P0 — must ship first, before lifecycle)

These are standalone fixes that don't depend on the lifecycle module.

### Fix 1: Call Eligibility — place_calls.py

**File:** `campaigns/management/commands/place_calls.py`

**Change:** Lines 83-87. Replace denylist with allowlist.

```python
# BEFORE (denylist — wrong):
).exclude(
    status__in=['new', 'opted_out', 'not_interested', 'demo_scheduled', 'design_partner'],
)

# AFTER (allowlist — correct):
).filter(
    status__in=['interested', 'engaged', 'follow_up_later'],
)
```

Rationale: calls are a warm-touch channel. Only prospects who have signalled intent
(`interested`, `engaged`) or explicitly said "call me later" (`follow_up_later`) 
should be called.

### Fix 2: Dynamic First Message — call_service.py

**File:** `campaigns/call_service.py`

**Change:** Add `first_message: str = ''` parameter to `place_call()`. When provided, skip the `_get_first_message()` lookup.

```python
@staticmethod
def place_call(
    phone_number: str,
    assistant_id: str,
    phone_number_id: str,
    prospect_name: str = '',
    company_name: str = '',
    segment: str = '',
    first_message: str = '',      # NEW
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ...
    resolved_first_message = first_message or CallService._get_first_message(
        assistant_id, segment, prospect_name
    )
    payload = {
        ...
        'assistantOverrides': {
            'firstMessage': resolved_first_message,   # was using stale lookup
            ...
        },
    }
```

**In place_calls.py:** Pass the dynamic_first_message:
```python
result = CallService.place_call(
    ...
    first_message=dynamic_first_message or '',
)
```

### Fix 3: Render {{FNAME}} in static CallScript

**File:** `campaigns/call_service.py`, method `_get_first_message`

**Change:** Add `prospect_name` parameter and render template vars before returning.

```python
@staticmethod
def _get_first_message(assistant_id: str, segment: str, prospect_name: str = '') -> str:
    ...
    if script:
        msg = script.first_message
        msg = msg.replace('{{FNAME}}', prospect_name or 'there')
        msg = msg.replace('{{NAME}}', prospect_name or 'there')
        return msg
```

### Fix 4: Wire channel_timing to static call path

**File:** `campaigns/management/commands/place_calls.py`

**Change:** Add channel_timing check before `CallService.place_call()` on the static path (flag_on=False).

```python
# Add after eligible query, inside the `for prospect in eligible:` loop,
# before `if dry_run:` block:
if not flag_on:
    from campaigns.services.channel_timing import can_place_call
    can, why = can_place_call(prospect)
    if not can:
        self.stdout.write(f'  skip (timing): {prospect.phone} — {why}')
        continue
```

### Fix 5: Enrich vapi_opener context

**File:** `campaigns/services/vapi_opener.py`

**Change:** Pass last inbound reply + pain signals into Claude prompt.

```python
def build_first_message(prospect: Prospect, brain: Brain) -> str:
    ...
    last_topic = get_last_topic(prospect)
    
    # NEW: pull last inbound reply snippet
    from campaigns.services.conversation import get_prospect_timeline
    timeline = get_prospect_timeline(prospect, days=60)
    last_inbound = next(
        (e for e in reversed(timeline) if e.direction == 'in'), None
    )
    last_reply_snippet = (last_inbound.body[:300] if last_inbound else '')
    
    user_msg = (
        f'Prospect: {prospect.decision_maker_name or "there"} at '
        f'{prospect.business_name or "your company"}.\n'
        f'Last outbound topic: {last_topic}\n'
        f'Their last reply: {last_reply_snippet or "No reply on record"}\n'
        f'Current tools: {prospect.current_tools or "Unknown"}\n'
        f'Pain signals: {prospect.pain_signals or "None recorded"}\n\n'
        f'Write the two-sentence opener now.'
    )
```

---

## Post-Call Actions (Sprint 8B)

### Webhook: Queue Post-Call Emails

**File:** `campaigns/views.py`, function `vapi_webhook`

After saving the call_log and updating prospect status, queue follow-up emails:

```python
# Add after prospect.save() in vapi_webhook:
_queue_post_call_action(call_log, prospect)
```

```python
def _queue_post_call_action(call_log, prospect):
    """Queue the appropriate follow-up email after a call."""
    from campaigns.models import EmailQueue, EmailTemplate
    from django.utils import timezone
    from datetime import timedelta
    
    campaign = call_log.campaign
    if not campaign:
        return
    
    template_name = None
    delay_hours = 0
    
    if call_log.status == 'voicemail':
        template_name = 'post_call_voicemail'
        delay_hours = 4  # Give them time to check voicemail
    
    elif call_log.status == 'answered' and call_log.disposition in ('interested', 'send_info'):
        template_name = 'post_call_demo_link'
        delay_hours = 1  # Strike while iron is hot
    
    elif call_log.status == 'answered' and call_log.disposition == 'demo_booked':
        template_name = 'demo_confirmation'
        delay_hours = 0.5
    
    if not template_name:
        return
    
    tmpl = EmailTemplate.objects.filter(
        campaign=campaign,
        template_name=template_name,
        is_active=True,
    ).first()
    if not tmpl:
        return  # Template not configured yet — silent skip
    
    EmailQueue.objects.get_or_create(
        prospect=prospect,
        campaign=campaign,
        template=tmpl,
        status='pending',
        defaults={
            'send_after': timezone.now() + timedelta(hours=delay_hours),
            'triggered_by': 'vapi_webhook',
        },
    )
```

### EmailTemplate Seeds Required (after lifecycle migration)

These templates need to be seeded for each calling campaign:

| template_name | Subject | Purpose |
|---------------|---------|---------|
| `post_call_voicemail` | "Just left you a voicemail, {FNAME}" | Reference the call, keep it warm |
| `post_call_demo_link` | "Great chatting — here's the link" | Demo link follow-up after answered call |
| `demo_confirmation` | "Demo confirmed — here's what to expect" | Auto-confirmation when demo booked |

---

## Interested Limbo Fix (Sprint 8C)

### New management command: nudge_stale_leads

**File:** `campaigns/management/commands/nudge_stale_leads.py`

Runs daily (add to cron). Finds prospects stuck in `interested` or `engaged` with no activity for 7+ days and queues a nudge.

```python
"""
Nudge prospects stuck in warm states with no recent touch.
Run daily after send_sequences.

Rules:
  - interested/engaged, last_emailed_at > 7 days ago, no demo scheduled
  - Queue nudge email (template: 'warm_nudge')
  - After 14 days total: transition to follow_up_later
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from campaigns.models import Prospect, Campaign
from campaigns.services import lifecycle


class Command(BaseCommand):
    help = 'Nudge warm leads stuck without activity'

    def handle(self, *args, **options):
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)

        # 14-day: move to follow_up_later
        stale_14 = Prospect.objects.filter(
            status__in=['interested', 'engaged'],
            send_enabled=True,
            last_emailed_at__lte=fourteen_days_ago,
        )
        for p in stale_14:
            try:
                lifecycle.transition(
                    p, 'follow_up_later',
                    reason='nudge:14d_no_activity',
                    triggered_by='nudge_stale_leads',
                )
                self.stdout.write(f'  → follow_up_later: {p.email} ({p.business_name})')
            except ValueError as e:
                self.stdout.write(f'  skip: {e}')

        # 7-day: queue nudge email
        stale_7 = Prospect.objects.filter(
            status__in=['interested', 'engaged'],
            send_enabled=True,
            last_emailed_at__lte=seven_days_ago,
            last_emailed_at__gt=fourteen_days_ago,
        )
        for p in stale_7:
            from campaigns.services.lifecycle import _queue_email
            _queue_email(p, template='warm_nudge', triggered_by='nudge_stale_leads')
            self.stdout.write(f'  queued nudge: {p.email} ({p.business_name})')

        self.stdout.write('Done.')
```

---

## follow_up_later Re-entry (Sprint 8D)

### Add to nudge_stale_leads or create reactivate_leads command

```python
# In nudge_stale_leads.py handle() or separate reactivate_leads.py:

# Re-enter prospects whose follow_up_after date has passed
reactivate = Prospect.objects.filter(
    status='follow_up_later',
    send_enabled=True,
    follow_up_after__lte=now,
)
for p in reactivate:
    try:
        lifecycle.transition(
            p, 'contacted',
            reason='reactivate:follow_up_after_passed',
            triggered_by='nudge_stale_leads',
        )
        # Reset email count so they get the re-engagement sequence from seq 2
        # (not seq 1 — they've seen the intro already)
        p.emails_sent = 1
        p.save(update_fields=['emails_sent', 'updated_at'])
        self.stdout.write(f'  reactivated: {p.email} ({p.business_name})')
    except ValueError as e:
        self.stdout.write(f'  skip reactivate: {e}')
```

---

## Callers to Update

Every place that currently does `prospect.status = X` must become `lifecycle.transition(prospect, X, reason, triggered_by)`.

| File | Line(s) | Current | Triggered_by label |
|------|---------|---------|-------------------|
| `place_calls.py` | ~160 | `prospect.status = 'contacted'` | `'place_calls'` |
| `views.py (vapi_webhook)` | ~742-749 | `prospect.status = 'demo_scheduled'` etc | `'vapi_webhook'` |
| `check_replies.py` | multiple | `prospect.status = 'interested'` etc | `'check_replies'` |
| `handle_replies.py` | multiple | via apply_reply_outcome | `'handle_replies'` |

**Do NOT** update:
- Django admin — intentional override, fine as-is
- `send_sequences` — it only sets `new → contacted` which lifecycle handles

---

## Migration Strategy

### Phase 1A (P0 bugs — no migration needed)
- Fix call eligibility (allowlist)
- Fix dynamic_first_message passing to Vapi
- Fix {{FNAME}} rendering
- Wire channel_timing to static path
- Enrich vapi_opener context

**Deploy:** Local + EC2 (restart cron containers). Zero downtime.

### Phase 1B (Lifecycle module + ProspectEvent)
- Create `ProspectEvent` model + migration
- Create `campaigns/services/lifecycle.py`
- Update callers one file at a time
- Verify with: `python manage.py shell -c "from campaigns.services.lifecycle import transition; print('ok')"`

**Deploy:** Apply migration on local first, verify, then EC2.
**Rollback:** If migration fails, lifecycle.py can be deleted — it's purely additive.

### Phase 2 (Post-call actions)
- Add `_queue_post_call_action` to vapi_webhook
- Seed `post_call_voicemail` and `post_call_demo_link` templates
- Add to cron: `nudge_stale_leads`

### Phase 3 (follow_up_later re-entry)
- Add re-entry logic to nudge_stale_leads
- Verify follow_up_after field is populated (it exists in migration 0007)

---

## Cron Schedule Addition

Add to `docker/cron-entrypoint.sh` after Phase 2 is deployed:

```bash
# Nudge stale warm leads + reactivate follow_up_later (daily, Mon-Fri, 11:30am — after send_sequences)
30 11 * * 1-5 cd /app && python manage.py nudge_stale_leads >> /tmp/outreach_nudge.log 2>&1
```

---

## Task Board

| # | Task | Phase | Size | Dependencies | Status |
|---|------|-------|------|--------------|--------|
| 1 | Fix call eligibility (allowlist in place_calls.py) | 1A | XS | None | Pending |
| 2 | Fix dynamic_first_message (CallService.place_call signature) | 1A | S | None | Pending |
| 3 | Fix {{FNAME}} rendering in _get_first_message | 1A | XS | Task 2 | Pending |
| 4 | Wire channel_timing to static call path | 1A | XS | None | Pending |
| 5 | Enrich vapi_opener with reply body + pain signals | 1A | S | None | Pending |
| 6 | Create ProspectEvent model + migration | 1B | S | None | Pending |
| 7 | Create campaigns/services/lifecycle.py | 1B | M | Task 6 | Pending |
| 8 | Update place_calls.py callers to use lifecycle.transition | 1B | S | Task 7 | Pending |
| 9 | Update vapi_webhook callers to use lifecycle.transition | 1B | S | Task 7 | Pending |
| 10 | Update check_replies.py callers to use lifecycle.transition | 1B | M | Task 7 | Pending |
| 11 | Add _queue_post_call_action to vapi_webhook | 2 | S | Task 9 | Pending |
| 12 | Seed post_call_voicemail + post_call_demo_link templates | 2 | S | Task 11 | Pending |
| 13 | Create nudge_stale_leads management command | 2 | M | Task 7 | Pending |
| 14 | Add nudge_stale_leads to cron schedule | 2 | XS | Task 13 | Pending |
| 15 | follow_up_later re-entry in nudge_stale_leads | 3 | S | Task 13 | Pending |
| 16 | Run full regression: send_sequences, place_calls, check_replies dry-run | 3 | S | All | Pending |
| 17 | Deploy migration to EC2 | 3 | S | Task 6 | Pending |

---

## Implementation Contract for Engineers

### DO:
- All `prospect.status` writes go through `lifecycle.transition()`
- Wrap every `lifecycle.transition()` call in `try/except ValueError` and log the skip
- Every `ProspectEvent` row must have `triggered_by` populated
- Side effects in `_fire_side_effects` must be wrapped individually in try/except
- Test with `--dry-run` flags before live runs

### DO NOT:
- Direct `prospect.status = X` outside Django admin or lifecycle.py
- Add new status values without updating `ALLOWED_TRANSITIONS`
- Let a side effect failure propagate and roll back the transition
- Skip the channel_timing check before any call placement
- Hard-code template names in views — use `template_name` constants

### File Structure (no new directories needed):
```
campaigns/services/lifecycle.py       ← NEW
campaigns/models.py                   ← add ProspectEvent
campaigns/migrations/0XXX_prospect_event.py  ← generated
campaigns/management/commands/nudge_stale_leads.py  ← NEW
campaigns/services/vapi_opener.py     ← enrich context
campaigns/call_service.py             ← first_message param
campaigns/management/commands/place_calls.py  ← eligibility + timing
campaigns/views.py                    ← post-call queue
```

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| lifecycle.transition raises ValueError on a legitimate transition we forgot to allow | Medium | Wrap all callers in try/except; log and skip rather than crash |
| Post-call email templates not seeded before vapi_webhook tries to queue | Low | _queue_email silently returns if template not found |
| nudge_stale_leads moves a prospect to follow_up_later while Claude is mid-reply | Low | handle_replies uses a DB transaction; lifecycle.transition is idempotent on same-status |
| EC2 migration out of sync with local | Low | Always apply migration to local first, verify schema, then EC2 |
| {{FNAME}} rendering change breaks a CallScript that doesn't use it | None | Replace is a no-op if var not present |

---

## Sprint 8 Progress Tracker

See `docs/sprint-8-progress.md` (created alongside this doc).
Chief Orchestrator updates that file after each task completes.

---

## CTO Sign-off

This plan is approved. Implement in phase order. Do not jump to Phase 2 until all Phase 1A bugs are fixed and verified. The lifecycle gateway (Phase 1B) must be deployed before any post-call actions or nudge logic — the side effect system depends on it.

**Priority override:** If the `interested` limbo is actively losing warm leads, implement Task 13 (nudge command) independently of the lifecycle module using direct status updates as a bridge, then migrate to lifecycle.transition later.
