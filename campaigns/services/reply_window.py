"""G2 — reply-window business-hours gate for AI auto-replies.

Pure, timezone-aware, zero side effects. Given a `Campaign` row and an
optional `now` datetime, returns True iff the current moment falls
inside the campaign's configured reply window (start/end hour on a
permitted weekday in the campaign's declared IANA timezone).

Usage from `handle_replies`:

    from campaigns.services.reply_window import is_within_reply_window
    if not is_within_reply_window(inbound.campaign):
        skip_inbound('outside reply window')

Config source of truth is `Campaign.reply_window_*` (migration 0019).
Each campaign can carry its own hours, weekdays, and timezone, so a
design partner in PST can have a PST window while TaggIQ stays on
Europe/Dublin. No globals, no environment variables.

This module is intentionally used by the flag=False live path. When a
campaign is migrated to `use_context_assembler=True` (Sprint 7 brain),
`rules_engine.timing_window(brain)` takes over and reads from
`ProductBrain.timing_rules` instead. Both paths share the same intent:
never auto-reply outside configured business hours.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _parse_weekdays(csv: str) -> set[int]:
    """Parse '0,1,2,3,4' into {0, 1, 2, 3, 4}. Silent on bad entries."""
    out: set[int] = set()
    for chunk in (csv or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            n = int(chunk)
        except ValueError:
            continue
        if 0 <= n <= 6:
            out.add(n)
    return out


def is_within_reply_window(campaign, now: Optional[datetime] = None) -> bool:
    """Return True iff `now` falls inside `campaign`'s reply window.

    Args:
        campaign: Campaign model instance with `reply_window_timezone`,
            `reply_window_start_hour`, `reply_window_end_hour`, and
            `reply_window_days` fields populated (migration 0019).
        now: Optional aware or naive datetime. If None, uses current
            UTC time. If naive, treated as UTC. Timezone-converted to
            the campaign's local timezone before the hour/weekday check.

    Returns:
        True if the current moment is within the window.
        False if outside the window OR if the campaign timezone is
        unparseable (fail closed — if we cannot determine local time,
        do NOT auto-reply).
    """
    if campaign is None:
        return False

    tz_name = getattr(campaign, 'reply_window_timezone', None) or 'Europe/Dublin'
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        # Fail closed: unparseable timezone means we do not auto-reply.
        # This surfaces the misconfiguration via "no replies going out"
        # which is louder and safer than silently using a wrong zone.
        return False

    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo('UTC'))
    local = now.astimezone(tz)

    allowed_days = _parse_weekdays(
        getattr(campaign, 'reply_window_days', '0,1,2,3,4')
    )
    if local.weekday() not in allowed_days:
        return False

    start_hour = int(getattr(campaign, 'reply_window_start_hour', 9) or 0)
    end_hour = int(getattr(campaign, 'reply_window_end_hour', 18) or 23)

    # Inclusive on start, exclusive on end — so 9..18 means "open at 9:00,
    # last reply at 17:59:59". Matches how people read "9-to-6 business
    # hours" in practice.
    return start_hour <= local.hour < end_hour
