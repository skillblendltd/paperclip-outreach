"""Sprint 7 — deterministic rules engine.

This module is the ONLY place that interprets a Brain's JSON fields into
decisions. Zero LLM calls. Every function here is pure (given brain + state
-> decision), fully unit-testable, and cheap.

Rules-engine contract with next_action.py:
    - decide_channel_and_when(brain, state, prospect) -> (channel, reason, wait_until)
    - apply_reply_outcome(brain, prospect, inbound) -> OutcomeEffect
    - apply_call_outcome(brain, prospect, call_log) -> OutcomeEffect
    - should_escalate(brain, prospect, event) -> (escalate, reason)
    - is_win(brain, prospect) -> bool

All four rule shapes (sequence_rules, timing_rules, call_eligibility,
escalation_rules) are documented in docs/sprint-7-implementation-plan.md
Section 2.3. JSONSchema files for each live in campaigns/brain_schemas/.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from campaigns.services.brain import Brain


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OutcomeEffect:
    """What the rules engine wants the executor to persist after an event."""
    new_status: Optional[str] = None
    handoff: Optional[str] = None        # 'ai_reply' | 'escalation' | None
    next_channel: Optional[str] = None   # 'email' | 'call' | None
    wait_hours: int = 0
    reason: str = ''


# ---------------------------------------------------------------------------
# Core decisions
# ---------------------------------------------------------------------------

def is_terminal(brain: Brain, status: str) -> bool:
    return status in (brain.terminal_states or [])


def should_escalate(brain: Brain, prospect, trigger: dict) -> Tuple[bool, str]:
    """Return (escalate, reason) given a trigger context.

    `trigger` is a dict like:
        {'type': 'reply', 'body': '...', 'status': 'interested', 'reply_count': 2}
    Rules consulted:
        escalation_rules.on_keyword     -> list[str], match any substring in body
        escalation_rules.on_status      -> list[str], match status
        escalation_rules.on_reply_count_gte -> int
    """
    rules = brain.escalation_rules or {}

    keywords = rules.get('on_keyword') or []
    body = (trigger.get('body') or '').lower()
    for kw in keywords:
        if kw and kw.lower() in body:
            return True, f'keyword:{kw}'

    statuses = rules.get('on_status') or []
    if trigger.get('status') in statuses:
        return True, f'status:{trigger["status"]}'

    threshold = rules.get('on_reply_count_gte')
    if threshold is not None and trigger.get('reply_count', 0) >= threshold:
        return True, f'reply_count_gte:{threshold}'

    return False, ''


def next_sequence_step(brain: Brain, current_status: str) -> dict:
    """Return the sequence-step dict for the current prospect status.

    Shape: {'next': 'seq1'|'seq_next'|None, 'after_hours': int, 'handoff': str|None}
    Unknown status returns an empty dict (= do nothing).
    """
    rules = brain.sequence_rules or {}
    return dict(rules.get(current_status) or {})


def is_eligible_for_call(brain: Brain, prospect, state) -> Tuple[bool, str]:
    """Check call_eligibility config against prospect + conversation state.

    Rules consulted:
        min_emails_sent     -> prospect.emails_sent >= N
        require_phone       -> prospect.phone must be non-empty
        skip_if_replied     -> if state.has_any_reply, block
        allowed_countries   -> prospect.region in list (empty list = allow all)
        max_calls_per_prospect -> prospect.calls_sent < N
    """
    rules = brain.call_eligibility or {}
    timing = brain.timing_rules or {}

    if rules.get('require_phone', True) and not (prospect.phone or ''):
        return False, 'no_phone'

    min_emails = rules.get('min_emails_sent', 0)
    if (prospect.emails_sent or 0) < min_emails:
        return False, f'min_emails_sent<{min_emails}'

    if rules.get('skip_if_replied', True) and getattr(state, 'has_any_reply', False):
        return False, 'already_replied'

    allowed = rules.get('allowed_countries') or []
    if allowed and (prospect.region or '') not in allowed:
        return False, f'country_not_allowed:{prospect.region}'

    max_calls = timing.get('max_calls_per_prospect') or rules.get('max_calls_per_prospect')
    if max_calls is not None and (prospect.calls_sent or 0) >= max_calls:
        return False, f'max_calls_per_prospect:{max_calls}'

    return True, 'eligible'


def apply_reply_outcome(brain: Brain, prospect, inbound) -> OutcomeEffect:
    """Return the state transition that should happen after we receive a reply.

    Maps InboundEmail.classification -> (new_status, handoff).
    Escalation check runs regardless — if it fires, we hand off to escalation
    AND still update status.
    """
    classification = (getattr(inbound, 'classification', '') or '').lower()

    # Canonical mappings. These are platform constants, not brain-configurable,
    # because they reflect the meaning of the classification labels themselves.
    status_map = {
        'opt_out':        'opted_out',
        'bounce':         'bounce',
        'not_interested': 'not_interested',
        'interested':     'interested',
        'question':       'engaged',
        'out_of_office':  prospect.status,  # no change, wait it out
        'other':          prospect.status,
    }
    new_status = status_map.get(classification, prospect.status)

    handoff = None
    if classification in ('interested', 'question'):
        handoff = 'ai_reply'
    elif classification in ('opt_out', 'bounce', 'not_interested'):
        handoff = None  # terminal, no reply

    trigger = {
        'type': 'reply',
        'body': getattr(inbound, 'body_text', '') or '',
        'status': new_status,
        'reply_count': getattr(prospect, 'reply_count', 0) or 0,
    }
    escalate, reason = should_escalate(brain, prospect, trigger)
    if escalate:
        handoff = 'escalation'

    return OutcomeEffect(
        new_status=new_status if new_status != prospect.status else None,
        handoff=handoff,
        reason=reason or f'classification:{classification}',
    )


def apply_call_outcome(brain: Brain, prospect, call_log) -> OutcomeEffect:
    """Return the state transition after a Vapi call lands.

    `call_log` is a CallLog row with `.disposition` ('answered', 'voicemail',
    'no_answer', 'busy', 'failed') and `.outcome` (free text tag).
    """
    disposition = (getattr(call_log, 'disposition', '') or '').lower()
    outcome = (getattr(call_log, 'outcome', '') or '').lower()

    # Answered + clear interest signal -> engaged
    if disposition == 'answered' and 'interest' in outcome:
        return OutcomeEffect(new_status='interested', handoff='ai_reply',
                             reason=f'call_answered_interest')
    # Answered but said no
    if disposition == 'answered' and ('not_interest' in outcome or 'decline' in outcome):
        return OutcomeEffect(new_status='not_interested', reason='call_declined')
    # Answered and asked for a callback / demo
    if disposition == 'answered' and ('demo' in outcome or 'meeting' in outcome):
        return OutcomeEffect(new_status='demo_scheduled', reason='call_demo_booked')
    # Voicemail / no answer -> keep status, schedule email follow-up
    if disposition in ('voicemail', 'no_answer', 'busy'):
        return OutcomeEffect(next_channel='email', wait_hours=48,
                             reason=f'call_no_contact:{disposition}')
    # Failure -> escalate for manual review
    if disposition == 'failed':
        return OutcomeEffect(handoff='escalation', reason='call_failed')
    return OutcomeEffect(reason=f'call_noop:{disposition}')


def is_win(brain: Brain, prospect) -> bool:
    primary = (brain.success_signals or {}).get('primary')
    if primary and prospect.status == primary:
        return True
    secondary = (brain.success_signals or {}).get('secondary') or []
    return prospect.status in secondary


# ---------------------------------------------------------------------------
# Timing helpers (consulted by channel_timing.py callers AND rules_engine)
# ---------------------------------------------------------------------------

def timing_window(brain: Brain) -> dict:
    """Return the timing config with defaults applied."""
    defaults = {
        'min_hours_since_inbound': 24,
        'min_hours_since_email':   48,
        'min_hours_since_call':    48,
        'max_emails_per_week':      3,
        'max_calls_per_prospect':   2,
    }
    return {**defaults, **(brain.timing_rules or {})}
