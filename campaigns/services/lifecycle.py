"""
Prospect Lifecycle Transition Gateway — Sprint 8.

This is the ONLY authorised way to change prospect.status outside of
Django admin. All calls from management commands, webhooks, and reply
handlers go through lifecycle.transition().

Design goals:
  1. Explicit allowed-transition map (no silent no-ops, no invalid jumps)
  2. Central side-effect declarations (demo -> queue email, opt_out -> suppress)
  3. Full audit trail via ProspectEvent
  4. Side-effect failures never roll back the transition itself

Usage:
    from campaigns.services.lifecycle import transition

    try:
        lifecycle.transition(
            prospect, 'interested',
            reason='reply:classification=interested',
            triggered_by='handle_replies',
        )
    except ValueError as exc:
        logger.warning('lifecycle skip: %s', exc)
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State machine definition
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    'new':             {'contacted'},
    'contacted':       {'interested', 'engaged', 'not_interested', 'opted_out', 'follow_up_later'},
    'engaged':         {'interested', 'not_interested', 'opted_out', 'demo_scheduled',
                        'follow_up_later', 'engaged'},
    'interested':      {'demo_scheduled', 'not_interested', 'opted_out',
                        'follow_up_later', 'engaged'},
    'demo_scheduled':  {'customer', 'design_partner', 'not_interested', 'follow_up_later'},
    'follow_up_later': {'contacted', 'interested', 'not_interested', 'opted_out'},
    'design_partner':  {'customer', 'demo_scheduled'},
    # opted_out, not_interested, customer — terminal for outbound, no transitions out
}

# Statuses where send_enabled should be forced off
SUPPRESS_ON_ENTER = {'opted_out', 'not_interested'}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transition(prospect, new_status: str, reason: str,
               triggered_by: str = 'system') -> Optional[object]:
    """Change prospect.status through the lifecycle gateway.

    Args:
        prospect:     Prospect model instance.
        new_status:   Target status string.
        reason:       Short description of why (e.g. 'reply:interested',
                      'call:voicemail', 'nudge:14d_no_activity').
        triggered_by: Which system component triggered this
                      (e.g. 'handle_replies', 'vapi_webhook', 'place_calls').

    Returns:
        ProspectEvent created, or None if no_op (same status).

    Raises:
        ValueError: If the transition is not allowed by ALLOWED_TRANSITIONS.
    """
    current = prospect.status or 'new'

    if new_status == current:
        return None  # No-op, not an error

    allowed = ALLOWED_TRANSITIONS.get(current, set())
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
    _fire_post_transition_hooks(prospect, event)
    return event


# ---------------------------------------------------------------------------
# Post-transition hooks (Sprint 9 — warm-trigger contextual calling)
# ---------------------------------------------------------------------------

def _fire_post_transition_hooks(prospect, event) -> None:
    """Fan out to registered hooks AFTER the transition + side effects have
    landed. Each hook is wrapped independently so a hook failure never rolls
    back the transition or blocks other hooks.

    Currently registered:
      - call_trigger.on_warm_transition (Sprint 9)
    """
    try:
        from campaigns.services.call_trigger import on_warm_transition
        on_warm_transition(prospect, event)
    except Exception as exc:
        logger.error(
            'lifecycle post-hook call_trigger failed prospect=%s: %s',
            prospect.id, exc,
        )


# ---------------------------------------------------------------------------
# Side effects — each block is independently try/except wrapped
# ---------------------------------------------------------------------------

def _fire_side_effects(prospect, from_status: str, to_status: str) -> None:
    """Fire declared side effects for entering a new state.

    Each effect is wrapped independently — a failure must never roll back
    the transition or block other effects.
    """
    if to_status in SUPPRESS_ON_ENTER:
        _effect_suppress(prospect, to_status)

    if to_status == 'demo_scheduled':
        _effect_queue_email(prospect, template='demo_confirmation',
                            delay_hours=0.5, triggered_by='lifecycle:demo_scheduled')

    elif to_status == 'follow_up_later':
        _effect_set_follow_up_date(prospect)


def _effect_suppress(prospect, to_status: str) -> None:
    try:
        if prospect.send_enabled:
            prospect.send_enabled = False
            prospect.save(update_fields=['send_enabled', 'updated_at'])

        if to_status == 'opted_out':
            _add_suppression(prospect, reason='opt_out')
    except Exception as exc:
        logger.error('lifecycle suppress effect failed prospect=%s: %s', prospect.id, exc)


def _effect_queue_email(prospect, template: str, delay_hours: float,
                        triggered_by: str) -> None:
    try:
        _queue_email(prospect, template=template, delay_hours=delay_hours,
                     triggered_by=triggered_by)
    except Exception as exc:
        logger.error('lifecycle queue_email effect failed prospect=%s template=%s: %s',
                     prospect.id, template, exc)


def _effect_set_follow_up_date(prospect) -> None:
    try:
        now = timezone.now()
        if not prospect.follow_up_after or prospect.follow_up_after < now:
            prospect.follow_up_after = now + timedelta(days=30)
            prospect.save(update_fields=['follow_up_after', 'updated_at'])
    except Exception as exc:
        logger.error('lifecycle follow_up_date effect failed prospect=%s: %s',
                     prospect.id, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _queue_email(prospect, template: str, delay_hours: float = 0,
                 triggered_by: str = 'lifecycle') -> None:
    """Queue a deferred email via EmailQueue.

    Silent no-op if template not configured for the campaign — this lets
    campaigns that don't have post-call templates skip gracefully without error.
    """
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
        logger.debug('lifecycle _queue_email: no template=%s for campaign=%s, skipping',
                     template, campaign.id)
        return

    send_after = timezone.now() + timedelta(hours=delay_hours)
    EmailQueue.objects.get_or_create(
        prospect=prospect,
        campaign=campaign,
        template=tmpl,
        status='pending',
        defaults={
            'send_after': send_after,
            'ab_variant': '',
            'triggered_by': triggered_by,
        },
    )
    logger.info('lifecycle queued email template=%s for prospect=%s', template, prospect.id)


def _add_suppression(prospect, reason: str = 'opt_out') -> None:
    """Add product-scoped email suppression."""
    from campaigns.models import Suppression

    campaign = prospect.campaign
    if not campaign or not campaign.product_ref:
        return
    if not prospect.email:
        return

    Suppression.objects.get_or_create(
        product=campaign.product_ref,
        email=prospect.email.lower(),
        defaults={'reason': reason},
    )
