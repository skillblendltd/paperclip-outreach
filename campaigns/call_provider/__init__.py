"""Provider-agnostic call dispatch boundary.

Paperclip's call code uses ONLY the artefacts in `base.py`:
  - `CallPrompt`     — fully-rendered prompt + facts produced by Paperclip
  - `CallProvider`   — Protocol every provider adapter conforms to
  - `CallEvent`      — normalized webhook outcome (provider-agnostic)
  - `place(prospect, prompt)` / `parse_webhook(slug, raw)` — entry points

Providers live as siblings (e.g. `vapi.py`). They translate Paperclip's
artefacts into the provider's wire format and translate the provider's
webhook events back into `CallEvent`. Provider-specific vocabulary
(`assistantOverrides`, `firstMessage`, etc.) MUST stay inside the adapter
file — anywhere else is a BLOCKER at review.

Adding a new provider = one new sibling file. No changes outside this
package.
"""
from campaigns.call_provider.base import (  # noqa: F401
    CallPrompt,
    CallEvent,
    CallProvider,
    place,
    parse_webhook,
    register,
    resolve,
)
