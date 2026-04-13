"""Sprint 7 Phase 7.2.3 — dynamic Vapi first_message builder.

Called by place_calls on the flag=True (use_context_assembler=True) path to
pre-compute a personalized 2-sentence opener that references the prospect's
last outbound touch. On any failure (no anthropic SDK installed, API error,
no topic history) we fall back to the brain's default CallScript.first_message
string so the call still goes through.

Design constraints (from sprint-7-implementation-plan.md Risk #11):
  - LLM call happens here at QUEUE TIME, not mid-call. Vapi consumes the
    pre-computed string.
  - Sonnet 4.6 floor. Brain.jobs['call_opener'] overrides the model.
  - Every call writes AIUsageLog with feature='call_analysis' (closest
    existing FEATURE_CHOICES bucket — adding 'call_opener' would require a
    migration, out of scope for Phase 7.2).
  - brain_version stamped on every row.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Optional

from campaigns.models import AIUsageLog, CallScript, Prospect
from campaigns.services.brain import Brain
from campaigns.services.conversation import get_last_topic

logger = logging.getLogger(__name__)


def build_first_message(prospect: Prospect, brain: Brain) -> str:
    """Return a 2-sentence Vapi opener for this prospect.

    Always returns a non-empty string. Falls back to the brain's
    CallScript.first_message (or a generic opener) when the LLM path fails.
    """
    fallback = _fallback_first_message(prospect, brain)

    last_topic = get_last_topic(prospect)
    if not last_topic:
        # Nothing to reference — static fallback is the correct behavior.
        return fallback

    try:
        import anthropic  # noqa: WPS433 — optional dep
    except ImportError:
        logger.info('vapi_opener: anthropic SDK not installed, using fallback')
        return fallback

    job = brain.job('call_opener')
    model = job.get('model', 'claude-sonnet-4-6')
    max_tokens = int(job.get('max_tokens', 120))

    system_prompt = (
        'You are writing the first spoken line an AI voice agent will say when '
        'it dials a prospect. Two short sentences max. Reference the last '
        'outbound touch naturally, then ask for 60 seconds. No em dashes. No '
        'pricing. Sound like a colleague following up, not a telemarketer.'
    )
    user_msg = (
        f'Prospect: {prospect.decision_maker_name or "there"} at '
        f'{prospect.business_name or "your company"}.\n'
        f'Last outbound topic: {last_topic}\n\n'
        f'Write the two-sentence opener now.'
    )

    started = time.monotonic()
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_msg}],
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        text = ''
        for block in resp.content:
            if getattr(block, 'type', '') == 'text':
                text += getattr(block, 'text', '')
        text = text.strip()
        if not text:
            logger.warning('vapi_opener: empty LLM response, falling back')
            return fallback

        _log_usage(
            prospect=prospect,
            brain=brain,
            model=model,
            input_tokens=getattr(resp.usage, 'input_tokens', 0),
            output_tokens=getattr(resp.usage, 'output_tokens', 0),
            latency_ms=latency_ms,
            success=True,
        )
        return text
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning(f'vapi_opener: LLM call failed ({exc}), using fallback')
        _log_usage(
            prospect=prospect,
            brain=brain,
            model=model,
            input_tokens=0,
            output_tokens=0,
            latency_ms=latency_ms,
            success=False,
            error_message=str(exc)[:500],
        )
        return fallback


def _fallback_first_message(prospect: Prospect, brain: Brain) -> str:
    """Resolve the static CallScript first_message from the brain, then from
    the prospect's campaign, then a generic string.
    """
    if brain.call_script_default_id:
        try:
            cs = CallScript.objects.get(id=brain.call_script_default_id)
            if cs.first_message:
                return cs.first_message
        except CallScript.DoesNotExist:
            pass
    # Fall back to a per-campaign CallScript if one exists for the segment.
    campaign = prospect.campaign
    if campaign is not None:
        cs = CallScript.objects.filter(campaign=campaign).first()
        if cs and cs.first_message:
            return cs.first_message
    name = prospect.decision_maker_name or 'there'
    return f'Hi {name}, do you have 60 seconds? I sent you a note recently and wanted to follow up.'


def _log_usage(*, prospect, brain, model, input_tokens, output_tokens,
               latency_ms, success, error_message=''):
    """Write an AIUsageLog row with brain_version stamped."""
    campaign = prospect.campaign
    product = campaign.product_ref if campaign else None
    org = product.organization if product else None
    if not org:
        return
    try:
        AIUsageLog.objects.create(
            organization=org,
            product=product,
            campaign=campaign,
            prospect=prospect,
            feature='call_analysis',
            model=model,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            cost_usd=_estimate_cost(input_tokens or 0, output_tokens or 0),
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            brain_version=brain.brain_version,
        )
    except Exception as exc:  # never let logging fail the caller
        logger.warning(f'vapi_opener: AIUsageLog write failed: {exc}')


def _estimate_cost(input_tokens: int, output_tokens: int) -> Decimal:
    """Sonnet 4.6 pricing: $3/M input, $15/M output."""
    input_cost = Decimal('3.00') * Decimal(input_tokens) / Decimal('1000000')
    output_cost = Decimal('15.00') * Decimal(output_tokens) / Decimal('1000000')
    return (input_cost + output_cost).quantize(Decimal('0.0001'))
