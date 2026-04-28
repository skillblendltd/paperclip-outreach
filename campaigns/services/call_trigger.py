"""Warm-lead call trigger — the ONLY producer of CallTask rows.

Wired into `lifecycle.transition()` as a post-transition callback. When a
prospect transitions into a "warm" status, we enqueue a CallTask scheduled
for the next call window. process_call_queue (cron */5) picks it up.

Idempotency: at most one pending CallTask per prospect, enforced by
DB partial unique index. A re-firing transition (prospect flips back to
interested from a second reply) updates the existing task instead of
inserting a duplicate.

Architectural rule: any other code creating a CallTask is a BLOCKER at
review.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.db import IntegrityError
from django.utils import timezone

logger = logging.getLogger(__name__)


# Statuses that warrant an outbound call. Mirrors the place_calls allowlist.
WARM_STATUSES = {'interested', 'engaged', 'follow_up_later'}


def on_warm_transition(prospect, event=None) -> Optional[object]:
    """Called by lifecycle after every status transition. No-ops unless the
    new status is warm. Returns the CallTask row (created or updated), or
    None if the trigger declined for any reason.

    Reasons for declining (logged but not raised):
      - status not in WARM_STATUSES
      - prospect has no phone
      - prospect.send_enabled = False (operator pause)
      - prospect.calling_enabled = False (per-prospect opt-out, if field exists)
      - campaign.calling_enabled = False (campaign-wide pause)
    """
    from campaigns.models import CallTask

    new_status = getattr(prospect, 'status', '') or ''
    if new_status not in WARM_STATUSES:
        return None

    skip = _eligibility_skip_reason(prospect)
    if skip:
        logger.info(
            'call_trigger: skip prospect=%s status=%s reason=%s',
            prospect.id, new_status, skip,
        )
        return None

    scheduled_for = _compute_scheduled_for(prospect)
    reason = f'warm:{getattr(event, "reason", "") or "transition"}'

    # Atomic upsert: if a pending CallTask already exists for this prospect,
    # update its scheduled_for / reason / triggering_event in place. The
    # partial unique index makes a second insert raise IntegrityError so
    # we update_or_create on (prospect, status='pending').
    try:
        task, created = CallTask.objects.update_or_create(
            prospect=prospect,
            status='pending',
            defaults={
                'scheduled_for': scheduled_for,
                'reason': reason[:200],
                'triggering_event': event,
            },
        )
    except IntegrityError as exc:
        # Rare race — another worker just inserted. Refresh and update.
        logger.warning('call_trigger: integrity race for prospect=%s: %s',
                       prospect.id, exc)
        task = CallTask.objects.filter(prospect=prospect, status='pending').first()
        if task:
            task.scheduled_for = scheduled_for
            task.reason = reason[:200]
            if event is not None:
                task.triggering_event = event
            task.save(update_fields=['scheduled_for', 'reason',
                                     'triggering_event', 'updated_at'])
        created = False

    logger.info(
        'call_trigger: %s task=%s prospect=%s scheduled_for=%s reason=%s',
        'CREATED' if created else 'UPDATED',
        task.id, prospect.id, scheduled_for, reason,
    )
    return task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eligibility_skip_reason(prospect) -> str:
    """Return a short skip reason string, or '' if eligible."""
    if not getattr(prospect, 'phone', ''):
        return 'no_phone'
    if not getattr(prospect, 'send_enabled', True):
        return 'send_disabled'

    campaign = getattr(prospect, 'campaign', None)
    if campaign is None:
        return 'no_campaign'
    if not getattr(campaign, 'calling_enabled', False):
        return 'campaign_calling_disabled'

    return ''


def _compute_scheduled_for(prospect):
    """Resolve the earliest UTC datetime when a call may dispatch. Falls back
    to `now` if channel_timing is unavailable for any reason.
    """
    try:
        from campaigns.services.channel_timing import next_call_window
        return next_call_window(prospect)
    except Exception as exc:
        logger.warning(
            'call_trigger: channel_timing.next_call_window failed for %s: %s',
            prospect.id, exc,
        )
        return timezone.now()
