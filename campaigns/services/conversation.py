"""
Conversation timeline service — the mini-CRM read layer.

Aggregates all interaction events for a prospect into one chronological timeline,
so downstream services (context_assembler, dynamic Vapi scripting, channel_timing)
can reason about "what has happened with this prospect" through ONE interface.

**CRITICAL ARCHITECTURAL RULE (from CTO review):**
This is the ONLY way any new code should query prospect history. Do not add
ad-hoc EmailLog / InboundEmail / CallLog queries in new features. Always go
through get_prospect_timeline() or the helpers in this module. Rationale:
without this firewall, we end up with 10 different versions of "get recent
touches" scattered across commands and the system becomes unmaintainable.

**AI ARCHITECT CONSTRAINT:**
This service makes ZERO LLM calls. All operations are pure DB reads. If you
find yourself reaching for an LLM to summarize or classify history, STOP —
that logic belongs elsewhere (the context_assembler does deterministic
token-budgeted truncation; the actual LLM call happens in handle_replies).
This service is a read view, not a summarizer.

Usage:
    from campaigns.services.conversation import (
        get_prospect_timeline,
        get_last_topic,
        get_conversation_state,
    )

    events = get_prospect_timeline(prospect, days=30)
    topic = get_last_topic(prospect)
    state = get_conversation_state(prospect)
"""
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

from django.utils import timezone

from campaigns.models import EmailLog, InboundEmail, CallLog


# ---------- data types ----------

@dataclass
class TimelineEvent:
    """A single interaction event on a prospect's timeline.

    kind:
      - 'outbound_email'  — we sent them an email (EmailLog row)
      - 'inbound_email'   — they replied to us (InboundEmail row)
      - 'outbound_call'   — we placed a call (CallLog row)
      - 'note'            — a manual or automated note stamped on the Prospect

    direction:
      - 'out' — we initiated (outbound touch)
      - 'in'  — prospect initiated (they wrote/called/replied to us)
      - 'internal' — notes, system events

    summary: one-line human-readable description of the event.
    body: full text content if relevant (email body, call transcript, note).
          Truncated/cleaned by the caller before injection into prompts.
    """
    at: 'timezone.datetime'
    kind: str
    direction: str
    summary: str
    body: str = ''
    source_id: str = ''  # UUID of the underlying row for traceability


@dataclass
class ConversationState:
    """Structured summary of the prospect's current conversation state.

    Used by channel_timing to enforce cross-channel locks and by
    context_assembler as a cheap header before the full timeline.
    """
    last_outbound_at: Optional['timezone.datetime'] = None
    last_inbound_at: Optional['timezone.datetime'] = None
    last_call_at: Optional['timezone.datetime'] = None
    last_outbound_channel: Optional[str] = None  # 'email' | 'call'
    total_outbound_touches: int = 0
    total_inbound_replies: int = 0
    total_calls: int = 0
    has_any_reply: bool = False
    events: List[TimelineEvent] = field(default_factory=list)


# ---------- public API ----------

def get_prospect_timeline(prospect, days: int = 30) -> List[TimelineEvent]:
    """Return a chronological list of all interaction events for this prospect.

    Args:
        prospect: Prospect model instance.
        days: How far back to look. Default 30. Use 0 for no limit (careful).

    Returns:
        List of TimelineEvent, sorted oldest-first. Empty list if no history.
    """
    if not prospect:
        return []

    since = timezone.now() - timedelta(days=days) if days else None

    events: List[TimelineEvent] = []

    # Outbound emails (EmailLog)
    out_qs = EmailLog.objects.filter(prospect=prospect)
    if since:
        out_qs = out_qs.filter(created_at__gte=since)
    for log in out_qs.order_by('created_at'):
        summary = _email_subject_summary(log.subject, log.template_name)
        events.append(TimelineEvent(
            at=log.created_at,
            kind='outbound_email',
            direction='out',
            summary=summary,
            body=log.body_html or '',
            source_id=str(log.id),
        ))

    # Inbound replies (InboundEmail)
    in_qs = InboundEmail.objects.filter(prospect=prospect)
    if since:
        in_qs = in_qs.filter(received_at__gte=since)
    for ie in in_qs.order_by('received_at'):
        summary = f'reply: {(ie.subject or "").strip()[:80]}'
        events.append(TimelineEvent(
            at=ie.received_at,
            kind='inbound_email',
            direction='in',
            summary=summary,
            body=ie.body_text or '',
            source_id=str(ie.id),
        ))

    # Outbound calls (CallLog)
    call_qs = CallLog.objects.filter(prospect=prospect)
    if since:
        call_qs = call_qs.filter(created_at__gte=since)
    for cl in call_qs.order_by('created_at'):
        disposition = getattr(cl, 'disposition', '') or getattr(cl, 'status', '') or 'placed'
        summary = f'call: {disposition}'
        body = getattr(cl, 'transcript', '') or ''
        events.append(TimelineEvent(
            at=cl.created_at,
            kind='outbound_call',
            direction='out',
            summary=summary,
            body=body,
            source_id=str(cl.id),
        ))

    # Sort everything chronologically
    events.sort(key=lambda e: e.at)
    return events


def get_last_topic(prospect) -> str:
    """Return a one-line summary of the most recent OUTBOUND touch.

    Used by dynamic Vapi script generation ("I sent you a note about
    {{last_topic}}...") and by context_assembler as a quick header.

    Returns empty string if no outbound history.
    """
    if not prospect:
        return ''
    last_out = EmailLog.objects.filter(prospect=prospect).order_by('-created_at').first()
    if not last_out:
        return ''
    return _email_subject_summary(last_out.subject, last_out.template_name)


def get_conversation_state(prospect) -> ConversationState:
    """Return structured conversation state for channel_timing + context_assembler.

    Cheap: three count queries + three max queries, no body fetches.
    """
    state = ConversationState()
    if not prospect:
        return state

    outbound = EmailLog.objects.filter(prospect=prospect)
    inbound = InboundEmail.objects.filter(prospect=prospect)
    calls = CallLog.objects.filter(prospect=prospect)

    state.total_outbound_touches = outbound.count()
    state.total_inbound_replies = inbound.count()
    state.total_calls = calls.count()
    state.has_any_reply = state.total_inbound_replies > 0

    last_out = outbound.order_by('-created_at').first()
    state.last_outbound_at = last_out.created_at if last_out else None

    last_in = inbound.order_by('-received_at').first()
    state.last_inbound_at = last_in.received_at if last_in else None

    last_call = calls.order_by('-created_at').first()
    state.last_call_at = last_call.created_at if last_call else None

    # Determine the most recent outbound channel (email vs call)
    if state.last_outbound_at and state.last_call_at:
        state.last_outbound_channel = 'call' if state.last_call_at > state.last_outbound_at else 'email'
    elif state.last_call_at:
        state.last_outbound_channel = 'call'
    elif state.last_outbound_at:
        state.last_outbound_channel = 'email'

    return state


# ---------- internal helpers ----------

def _email_subject_summary(subject: str, template_name: str = '') -> str:
    """Return a short, human-readable summary of an outbound email."""
    s = (subject or '').strip()
    if not s and template_name:
        return f'outbound: {template_name}'
    # Strip "Re: " / "Fwd: " prefixes for cleaner summaries
    cleaned = s
    while cleaned.lower().startswith(('re:', 'fwd:', 'fw:')):
        cleaned = cleaned.split(':', 1)[1].strip() if ':' in cleaned else cleaned
    return cleaned[:120]
