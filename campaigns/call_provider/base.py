"""Provider-agnostic call dispatch contract.

This module defines the boundary between Paperclip (which owns conversation
logic, prompts, scheduling, idempotency, lifecycle) and the underlying voice
provider (Vapi today, possibly Retell/Bland/Twilio+OpenAI tomorrow).

Architectural rule (CTO-enforced):
    No provider vocabulary above this line. The dataclasses below speak
    Paperclip's language. Each adapter (e.g. `vapi.py`) translates these
    into the provider's wire format.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


# ---------------------------------------------------------------------------
# Paperclip-native artefacts (provider speaks these, never the reverse)
# ---------------------------------------------------------------------------

@dataclass
class CallPrompt:
    """Fully-formed instructions for one outbound call.

    All fields are rendered server-side by Paperclip. No template syntax
    (e.g. `{{fname}}`) is allowed to leave Paperclip — adapters receive
    finished strings. `structured_facts` is the exception: short key/value
    pairs that an adapter MAY use for variable injection if the provider
    supports it. Whether or not the adapter uses structured_facts, the
    `system_prompt` and `first_message` strings are already complete.
    """

    system_prompt: str
    """The full system prompt for the call's LLM. Persona, rules, conversation
    history are all baked in. Capped at ~800 tokens by the prompt_builder."""

    first_message: str
    """What the AI says first when the prospect picks up. Fully rendered;
    no `{{vars}}` left."""

    structured_facts: dict[str, str] = field(default_factory=dict)
    """Short key/value pairs (fname, company, last_topic, current_tools, etc.).
    Adapters that support variable injection (Vapi `variableValues`) may use
    these; adapters that don't may ignore them."""

    guardrails: dict[str, object] = field(default_factory=dict)
    """Behaviour hints adapters map to provider config:
        max_duration_seconds: int
        can_end_call: bool
        can_transfer_to: Optional[str]   # E.164 phone
        voice_persona: str               # abstract label e.g. 'warm-irish-male'
    """

    correlation_id: str = ''
    """Paperclip's CallTask UUID (or similar). Echoed back via webhook so we
    can tie events to the originating task."""


@dataclass
class CallEvent:
    """Normalized webhook outcome from any provider.

    Adapters parse provider-specific webhook payloads and return one of these.
    """

    provider_call_id: str
    """The provider's identifier for the call. Stored in CallLog and CallTask."""

    correlation_id: str = ''
    """The CallTask UUID we sent in CallPrompt; echoed back."""

    event_type: str = ''
    """One of: 'started', 'answered', 'voicemail', 'no_answer', 'ended', 'failed'."""

    duration_seconds: int = 0
    """Total call duration. Zero for non-end events."""

    transcript: str = ''
    """Full transcript text. Empty until the call ends."""

    recording_url: str = ''
    """URL of the call recording (provider-hosted). Empty until the call ends."""

    summary: str = ''
    """Provider-generated short summary if available. Optional."""

    disposition: str = ''
    """Provider's intent classification mapped to Paperclip vocabulary:
       'interested' | 'demo_booked' | 'not_interested' | 'voicemail_left'
       | 'no_answer' | 'failed' | ''. May be empty when not derivable."""

    raw: dict = field(default_factory=dict)
    """Original payload, kept for debugging / re-derivation. Never written
    to user-facing fields."""


@dataclass
class CallResult:
    """Synchronous outcome of a place_call() request — placement only,
    not call completion. The actual call outcome comes via webhook."""

    success: bool
    provider_call_id: str = ''
    error: str = ''


# ---------------------------------------------------------------------------
# Provider Protocol
# ---------------------------------------------------------------------------

class CallProvider(Protocol):
    """Every adapter must implement this surface."""

    slug: str
    """Stable identifier, e.g. 'vapi'. Used for routing and webhook URLs."""

    def place_call(self, prospect, prompt: CallPrompt) -> CallResult:
        """Send the call to the provider. Returns provider_call_id on success.
        Implementation reads provider auth/IDs from settings or
        Campaign.provider_config (as the adapter sees fit)."""
        ...

    def parse_webhook(self, raw: dict) -> Optional[CallEvent]:
        """Translate a provider webhook payload into a CallEvent.

        Returns None if the payload is irrelevant (heartbeat, signature
        check, etc.). Raises only on malformed / corrupt payloads."""
        ...


# ---------------------------------------------------------------------------
# Registry — providers register themselves at import time
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, CallProvider] = {}


def register(provider: CallProvider) -> None:
    """Register a provider under its slug. Called once at import time by each
    adapter module."""
    _REGISTRY[provider.slug] = provider


def resolve(slug: str) -> CallProvider:
    """Return the provider for a given slug. Imports adapters lazily so each
    is registered before lookup."""
    # Side-effect imports — each adapter calls register() at module load.
    from campaigns import call_provider  # noqa: F401
    from campaigns.call_provider import vapi  # noqa: F401

    if slug not in _REGISTRY:
        raise KeyError(f'No call provider registered for slug={slug!r}. '
                       f'Known: {sorted(_REGISTRY)}')
    return _REGISTRY[slug]


def place(prospect, prompt: CallPrompt, provider_slug: str = 'vapi') -> CallResult:
    """Provider-agnostic dispatch entry point. Used by process_call_queue
    and any other code that wants to place a call.

    `provider_slug` defaults to 'vapi' for now. Future: read from
    Campaign.call_provider field.
    """
    provider = resolve(provider_slug)
    return provider.place_call(prospect, prompt)


def parse_webhook(provider_slug: str, raw: dict) -> Optional[CallEvent]:
    """Provider-agnostic webhook parsing. Used by the webhook view to
    normalize an incoming payload into a CallEvent."""
    provider = resolve(provider_slug)
    return provider.parse_webhook(raw)
