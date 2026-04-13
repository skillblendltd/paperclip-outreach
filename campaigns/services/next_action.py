"""Sprint 7 — next_action decision service.

Given a prospect, return what the executor should do: send email, place
call, wait, hand off, or declare terminal. Composes:
    brain.load_brain(prospect)
    conversation.get_conversation_state(prospect)
    channel_timing (existing) + rules_engine (this sprint)

THIS MODULE IS THE ONLY SOURCE OF "WHAT TO DO NEXT". Commands
(send_sequences, place_calls, handle_replies) must call decide_next_action()
on the flag=True path instead of hardcoding sequence-step-1 logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from campaigns.models import Prospect
from campaigns.services import channel_timing, conversation
from campaigns.services.brain import Brain, BrainNotFound, load_brain
from campaigns.services import rules_engine


@dataclass
class NextAction:
    """Platform-agnostic directive returned by decide_next_action()."""
    channel: Optional[str]           # 'email' | 'call' | None
    reason: str
    sequence_step: Optional[str] = None   # 'seq1', 'seq_next', etc
    wait_hours: int = 0
    handoff: Optional[str] = None         # 'ai_reply' | 'escalation' | None
    brain_version: int = 0


def decide_next_action(prospect: Prospect) -> NextAction:
    """Compute the next action for a prospect under its campaign's brain.

    Precedence (first match wins):
        1. Terminal status                     -> channel=None
        2. Escalation signal on current state  -> handoff='escalation'
        3. Sequence rule for current status    -> channel='email' + sequence_step
        4. Call eligibility                    -> channel='call'
        5. Otherwise                           -> channel=None, reason='waiting'

    The executor is expected to respect:
        - send window on the campaign
        - channel_timing locks (consulted here for decision + by executor at
          write time as a second safety check)
        - daily caps
    """
    try:
        brain = load_brain(prospect)
    except BrainNotFound as exc:
        return NextAction(channel=None, reason=f'no_brain:{exc}')

    # 1. Terminal?
    if rules_engine.is_terminal(brain, prospect.status or ''):
        return NextAction(
            channel=None,
            reason=f'terminal:{prospect.status}',
            brain_version=brain.brain_version,
        )

    state = conversation.get_conversation_state(prospect)

    # 2. Escalation check on current state
    escalate, reason = rules_engine.should_escalate(
        brain, prospect,
        trigger={
            'type': 'state',
            'body': '',
            'status': prospect.status,
            'reply_count': getattr(state, 'inbound_count', 0) or 0,
        },
    )
    if escalate:
        return NextAction(
            channel=None, handoff='escalation', reason=reason,
            brain_version=brain.brain_version,
        )

    # 3. Sequence rule
    step = rules_engine.next_sequence_step(brain, prospect.status or 'new')
    if step.get('next'):
        # Consult channel_timing — if email is blocked, return wait
        can, why = channel_timing.can_send_email(prospect)
        if not can:
            return NextAction(
                channel=None, reason=f'email_blocked:{why}',
                wait_hours=step.get('after_hours', 0),
                brain_version=brain.brain_version,
            )
        return NextAction(
            channel='email',
            sequence_step=step['next'],
            wait_hours=step.get('after_hours', 0),
            handoff=step.get('handoff'),
            reason=f'sequence:{step["next"]}',
            brain_version=brain.brain_version,
        )

    # 4. Call eligibility
    eligible, call_reason = rules_engine.is_eligible_for_call(brain, prospect, state)
    if eligible:
        can, why = channel_timing.can_place_call(prospect)
        if can:
            return NextAction(
                channel='call',
                reason=f'call_eligible:{call_reason}',
                brain_version=brain.brain_version,
            )
        return NextAction(
            channel=None,
            reason=f'call_blocked:{why}',
            brain_version=brain.brain_version,
        )

    # 5. Waiting
    return NextAction(
        channel=None,
        reason=f'waiting:status={prospect.status}',
        brain_version=brain.brain_version,
    )
