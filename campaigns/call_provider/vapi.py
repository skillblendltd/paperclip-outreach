"""Vapi adapter — translates Paperclip's CallPrompt / CallEvent into Vapi's
wire format and back.

This is the ONLY file that should know about Vapi's vocabulary
(`assistantOverrides`, `firstMessage`, `variableValues`, `end-of-call-report`,
etc.). Anywhere else using those terms is an architectural violation.

Provider auth (VAPI_API_KEY, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID) is read
from Django settings or per-campaign overrides on Campaign.vapi_assistant_id.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests
from django.conf import settings

from campaigns.call_provider.base import (
    CallEvent, CallProvider, CallPrompt, CallResult, register,
)

logger = logging.getLogger(__name__)

VAPI_API_URL = 'https://api.vapi.ai'
DEFAULT_TIMEOUT_SECONDS = 30


class VapiProvider:
    """Conforms to the CallProvider Protocol (duck-typed, no inheritance)."""

    slug = 'vapi'

    # ------------------------------------------------------------------
    # Outbound: Paperclip → Vapi
    # ------------------------------------------------------------------

    def place_call(self, prospect, prompt: CallPrompt) -> CallResult:
        api_key = getattr(settings, 'VAPI_API_KEY', '') or ''
        if not api_key:
            return CallResult(success=False, error='VAPI_API_KEY not configured')

        # Resolve provider IDs. Per-campaign override beats global default.
        campaign = getattr(prospect, 'campaign', None)
        assistant_id = ''
        if campaign is not None:
            assistant_id = getattr(campaign, 'vapi_assistant_id', '') or ''
        assistant_id = assistant_id or getattr(settings, 'VAPI_ASSISTANT_ID', '') or ''
        phone_number_id = getattr(settings, 'VAPI_PHONE_NUMBER_ID', '') or ''

        if not assistant_id:
            return CallResult(success=False, error='No assistant_id configured')
        if not phone_number_id:
            return CallResult(success=False, error='No phone_number_id configured')
        if not getattr(prospect, 'phone', ''):
            return CallResult(success=False, error='Prospect has no phone')

        payload = self._build_payload(prospect, prompt, assistant_id, phone_number_id)

        try:
            logger.info(
                f'[vapi] placing call to {prospect.phone} '
                f'({getattr(prospect, "business_name", "")})'
            )
            resp = requests.post(
                f'{VAPI_API_URL}/call/phone',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if resp.status_code in (200, 201):
                provider_call_id = resp.json().get('id', '') or ''
                logger.info(f'[vapi] call placed: {provider_call_id}')
                return CallResult(success=True, provider_call_id=provider_call_id)
            err = resp.text[:500]
            logger.error(f'[vapi] HTTP {resp.status_code}: {err}')
            return CallResult(success=False, error=err)
        except requests.RequestException as exc:
            logger.error(f'[vapi] request error: {exc}')
            return CallResult(success=False, error=str(exc))

    def _build_payload(self, prospect, prompt: CallPrompt,
                       assistant_id: str, phone_number_id: str) -> dict:
        """Translate CallPrompt → Vapi `assistantOverrides` shape.

        - `firstMessage`        ← prompt.first_message (already rendered)
        - `model.messages[0]`   ← prompt.system_prompt as system role
                                  (overrides whatever's in the dashboard)
        - `variableValues`      ← prompt.structured_facts (so any `{{var}}`
                                  remaining in the assistant's config gets
                                  filled, though Paperclip-rendered strings
                                  contain none)
        - `metadata`            ← correlation_id + a few key facts so they
                                  echo back via webhook
        """
        guardrails = prompt.guardrails or {}

        assistant_overrides: dict = {
            'firstMessage': prompt.first_message,
            'metadata': {
                'correlation_id': prompt.correlation_id,
                'prospect_id': str(getattr(prospect, 'id', '')),
                'prospect_name': getattr(prospect, 'decision_maker_name', '') or '',
                'company_name': getattr(prospect, 'business_name', '') or '',
                'segment': getattr(prospect, 'segment', '') or '',
            },
        }

        if prompt.structured_facts:
            # Vapi templates `{{key}}` in the assistant's config from this map.
            # Paperclip's rendered strings contain no `{{}}`, so this is purely
            # a belt-and-braces signal for any provider-side templates.
            assistant_overrides['variableValues'] = dict(prompt.structured_facts)

        if prompt.system_prompt:
            # Override the system prompt for THIS call only. Lets us keep the
            # Vapi dashboard assistant a thin shell — all prompt content lives
            # in Paperclip and travels per-call.
            assistant_overrides['model'] = {
                'messages': [
                    {'role': 'system', 'content': prompt.system_prompt},
                ],
            }

        max_dur = guardrails.get('max_duration_seconds')
        if isinstance(max_dur, int) and max_dur > 0:
            assistant_overrides['maxDurationSeconds'] = max_dur

        return {
            'assistantId': assistant_id,
            'phoneNumberId': phone_number_id,
            'customer': {
                'number': prospect.phone,
                'name': getattr(prospect, 'decision_maker_name', '') or 'there',
            },
            'assistantOverrides': assistant_overrides,
        }

    # ------------------------------------------------------------------
    # Inbound: Vapi webhook → CallEvent
    # ------------------------------------------------------------------

    def parse_webhook(self, raw: dict) -> Optional[CallEvent]:
        """Translate a Vapi webhook payload into a normalized CallEvent.

        Returns None for payloads we don't care about (heartbeats, function
        calls handled separately). Raises only on malformed JSON shape.
        """
        if not isinstance(raw, dict):
            return None

        message = raw.get('message', raw)
        message_type = (
            raw.get('message', {}).get('type', '')
            if 'message' in raw else raw.get('type', '')
        )

        if message_type != 'end-of-call-report':
            # function-call etc. — not a terminal event for our queue
            return None

        call_data = message.get('call', {}) if isinstance(message, dict) else {}
        provider_call_id = call_data.get('id', '') or ''
        metadata = (
            call_data.get('assistantOverrides', {}).get('metadata', {})
            if isinstance(call_data, dict) else {}
        )
        correlation_id = (metadata or {}).get('correlation_id', '') or ''

        # Duration
        duration_seconds = 0
        started, ended = call_data.get('startedAt', ''), call_data.get('endedAt', '')
        if started and ended:
            from datetime import datetime
            try:
                start_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(ended.replace('Z', '+00:00'))
                duration_seconds = int((end_dt - start_dt).total_seconds())
            except (ValueError, TypeError):
                duration_seconds = 0

        # Event type from Vapi's endedReason
        end_reason = (call_data.get('endedReason') or '').lower()
        if end_reason in ('customer-did-not-answer', 'customer-busy'):
            event_type = 'no_answer'
        elif end_reason == 'voicemail':
            event_type = 'voicemail'
        elif duration_seconds > 0:
            event_type = 'answered'
        else:
            event_type = 'ended'

        # Transcript / recording / summary
        transcript = message.get('transcript', '') or ''
        recording_url = message.get('recordingUrl', '') or ''
        summary = message.get('summary', '') or ''

        # Disposition from structuredData
        analysis = message.get('analysis', {}) if isinstance(message, dict) else {}
        structured = analysis.get('structuredData', {}) if isinstance(analysis, dict) else {}
        disposition = ''
        if structured.get('appointmentBooked'):
            disposition = 'demo_booked'
        elif structured.get('interested') is True:
            disposition = 'interested'
        elif structured.get('notInterested') is True:
            disposition = 'not_interested'
        elif structured.get('doNotCall') is True:
            disposition = 'do_not_call'

        if not summary:
            summary = (
                structured.get('callSummary', '') or analysis.get('summary', '') or ''
            )

        return CallEvent(
            provider_call_id=provider_call_id,
            correlation_id=correlation_id,
            event_type=event_type,
            duration_seconds=duration_seconds,
            transcript=transcript,
            recording_url=recording_url,
            summary=summary,
            disposition=disposition,
            raw=raw,
        )


# Register at import time
register(VapiProvider())
