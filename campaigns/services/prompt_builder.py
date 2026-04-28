"""Build a fully-rendered CallPrompt from a Prospect.

This is the boundary between Paperclip's domain knowledge and the
provider-agnostic call dispatch surface. Every string returned here is
already rendered — no `{{vars}}`, no provider-specific markers — so adapters
can ship them straight to whatever API is on the other side.

Composition:
  - persona / rules     ← PromptTemplate (DB) for the campaign's product
  - first_message       ← vapi_opener.build_first_message (Claude-generated)
  - conversation block  ← context_assembler.build_context_window (rule-based)
  - structured_facts    ← short key/value pairs for adapters that templatize
  - guardrails          ← max_duration_seconds, can_end_call, etc.

VOICE-CHANNEL TOKEN CAP: 800 tokens hard ceiling for the conversation block.
Bigger context inflates first-token latency on the call AND increases per-
minute cost — both worse on voice than email. If a future use case needs
more, justify it on cost/latency grounds first.
"""
from __future__ import annotations

import logging
from typing import Optional

from campaigns.call_provider.base import CallPrompt

logger = logging.getLogger(__name__)


VOICE_CONTEXT_TOKEN_CAP = 800
DEFAULT_MAX_DURATION_SECONDS = 300   # 5 minutes — typical warm-lead call


def build_call_prompt(prospect, *, correlation_id: str = '') -> CallPrompt:
    """Return a fully-rendered CallPrompt for `prospect`.

    Falls back gracefully on any sub-failure — a generic prompt is always
    returned so the call can still be placed. Errors are logged but not
    raised.
    """
    first_message = _build_first_message(prospect)
    system_prompt = _build_system_prompt(prospect)
    structured_facts = _build_structured_facts(prospect)
    guardrails = _build_guardrails(prospect)

    return CallPrompt(
        system_prompt=system_prompt,
        first_message=first_message,
        structured_facts=structured_facts,
        guardrails=guardrails,
        correlation_id=correlation_id,
    )


# ---------------------------------------------------------------------------
# Component builders
# ---------------------------------------------------------------------------

def _build_first_message(prospect) -> str:
    """Personalized opener via vapi_opener (Claude); falls back to a generic
    string if the LLM call fails or no brain is configured."""
    try:
        from campaigns.services.vapi_opener import build_first_message, _fallback_first_message
        from campaigns.services.brain import load_brain_by_product
        product_slug = ''
        try:
            product_slug = prospect.campaign.product_ref.slug
        except AttributeError:
            pass
        if product_slug:
            try:
                brain = load_brain_by_product(product_slug)
                return build_first_message(prospect, brain)
            except Exception as exc:
                logger.warning(
                    'prompt_builder: brain load failed (%s); using fallback opener',
                    exc,
                )
                # Try fallback through brain machinery only if a brain object
                # is available; otherwise build a generic line below.
        # No brain available — return a generic opener.
        name = getattr(prospect, 'decision_maker_name', '') or 'there'
        return f'Hi {name}, do you have 60 seconds? I sent you a note recently and wanted to follow up.'
    except Exception as exc:
        logger.warning('prompt_builder: first_message build failed: %s', exc)
        return 'Hi there, do you have 60 seconds? I sent you a note recently and wanted to follow up.'


def _build_system_prompt(prospect) -> str:
    """Concatenate persona + rules + conversation history into one fully-formed
    string, capped at VOICE_CONTEXT_TOKEN_CAP for the history section.
    """
    persona = _resolve_persona(prospect)
    history = _resolve_history_block(prospect)

    parts = [persona] if persona else []
    if history:
        parts.append(history)
    return '\n\n'.join(parts).strip()


def _resolve_persona(prospect) -> str:
    """Pull the call persona from PromptTemplate (feature='call_persona'),
    fallback to a baked default per product slug. The result is the
    fixed-rules portion of the system prompt — voice, what to say,
    what NOT to say, how to handle objections.
    """
    try:
        from campaigns.models import PromptTemplate
        product = None
        try:
            product = prospect.campaign.product_ref
        except AttributeError:
            pass
        if product:
            tmpl = PromptTemplate.objects.filter(
                product=product, feature='call_persona', is_active=True,
            ).order_by('-version').first()
            if tmpl and tmpl.template:
                return _render_no_provider_vars(tmpl.template, prospect)
    except Exception as exc:
        logger.warning('prompt_builder: persona PromptTemplate lookup failed: %s', exc)

    return _default_call_persona(prospect)


def _default_call_persona(prospect) -> str:
    """Generic warm-follow-up persona used when no PromptTemplate is configured.
    Stays short — most of the value comes from the conversation history below.
    """
    name = getattr(prospect, 'decision_maker_name', '') or 'there'
    company = getattr(prospect, 'business_name', '') or 'their business'
    product_slug = ''
    try:
        product_slug = prospect.campaign.product_ref.slug
    except AttributeError:
        pass
    if product_slug == 'taggiq':
        product_line = (
            'You are calling on behalf of TaggIQ, a POS platform for print and '
            'promo shops. The prospect previously engaged via email.'
        )
    elif product_slug == 'fullypromoted':
        product_line = (
            'You are calling on behalf of Fully Promoted Ireland (master '
            'franchise). The prospect previously engaged via email.'
        )
    else:
        product_line = 'You are following up on a previous email conversation.'

    return (
        f'{product_line}\n'
        f'Prospect: {name} at {company}.\n'
        f'\n'
        f'Rules:\n'
        f'- Be warm, specific, and brief. Reference what they said in their '
        f'reply rather than restarting from scratch.\n'
        f'- Do not quote prices or commit to specific dates / meeting times. '
        f'Offer to send a calendar link by email.\n'
        f'- If they ask to be removed, acknowledge and end politely.\n'
        f'- If you reach voicemail, leave a 15-second message referencing '
        f'their reply and saying we will email a calendar link.\n'
        f'- No em dashes. Use hyphens with spaces.\n'
        f'- If they ask a question you cannot answer, say "let me have Prakash '
        f'follow up by email with that" and offer to capture their email.'
    )


def _resolve_history_block(prospect) -> str:
    """Conversation history rendered for VOICE channel. Wrapped in
    <prospect_history> tags with the prompt-injection firewall preamble
    (same contract as email reply context_assembler usage).
    """
    try:
        from campaigns.services.context_assembler import build_context_window
        return build_context_window(
            prospect, max_tokens=VOICE_CONTEXT_TOKEN_CAP,
        )
    except Exception as exc:
        logger.warning('prompt_builder: context_assembler failed: %s', exc)
        return ''


def _build_structured_facts(prospect) -> dict[str, str]:
    """Short key/value pairs that adapters MAY use for variable injection.
    Paperclip-rendered strings already contain no `{{vars}}`, so this is a
    secondary signal — useful for any provider-side templates a future
    adapter might rely on.
    """
    facts: dict[str, str] = {}
    name = getattr(prospect, 'decision_maker_name', '') or ''
    if name:
        facts['fname'] = name.split()[0]
        facts['name'] = name
    company = getattr(prospect, 'business_name', '') or ''
    if company:
        facts['company'] = company
    segment = getattr(prospect, 'segment', '') or ''
    if segment:
        facts['segment'] = segment
    tools = getattr(prospect, 'current_tools', '') or ''
    if tools:
        facts['current_tools'] = tools[:200]
    pain = getattr(prospect, 'pain_signals', '') or ''
    if pain:
        facts['pain_signals'] = pain[:200]

    try:
        from campaigns.services.conversation import get_last_topic
        topic = get_last_topic(prospect) or ''
        if topic:
            facts['last_topic'] = topic[:200]
    except Exception:
        pass

    return facts


def _build_guardrails(prospect) -> dict[str, object]:
    """Behaviour hints adapters map to provider config."""
    return {
        'max_duration_seconds': DEFAULT_MAX_DURATION_SECONDS,
        'can_end_call': True,
        'can_transfer_to': None,
        'voice_persona': 'warm-irish',  # abstract; adapter maps to a voice ID
    }


def _render_no_provider_vars(template: str, prospect) -> str:
    """Render Paperclip-side template variables in a PromptTemplate string.
    No `{{}}` tokens leave Paperclip — adapters never see un-rendered text.
    """
    name = getattr(prospect, 'decision_maker_name', '') or 'there'
    company = getattr(prospect, 'business_name', '') or ''
    return (
        template
        .replace('{{FNAME}}', name.split()[0] if name else 'there')
        .replace('{{NAME}}', name)
        .replace('{{COMPANY}}', company)
    )
