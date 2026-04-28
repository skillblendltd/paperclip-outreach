"""
Channel timing lock service — prevents cross-channel conflicts.

Without this, the system could:
  - Call a prospect 2h after they replied via email (awkward, broken continuity)
  - Send an email to a prospect 30 minutes after we called them (feels robotic)
  - Re-send to a prospect who already replied but wasn't yet marked replied
    (race conditions during reply processing)

This service is a pure read layer. It returns (allowed, reason) booleans that
outbound code paths consult BEFORE placing a touch. Gap thresholds are
configurable per-call so different campaigns can have different rules.

**Phase 2A status:** The service exists but is NOT yet wired into send_sequences
or place_calls. That's Phase 2B work (live code touch). In Phase 2A we just
build the library so it's ready to plug in once Phase 1 produces real data and
we validate the thresholds.

Usage:
    from campaigns.services.channel_timing import can_send_email, can_place_call

    ok, reason = can_send_email(prospect, min_hours_since_inbound=24)
    if not ok:
        log.info(f'skipping email for {prospect.email}: {reason}')
        return

    ok, reason = can_place_call(prospect, min_hours_since_email=48)
    if not ok:
        log.info(f'skipping call for {prospect.email}: {reason}')
        return
"""
from datetime import timedelta
from typing import Tuple

from django.utils import timezone

from campaigns.services.conversation import get_conversation_state


# Default thresholds — can be overridden per call.
DEFAULT_MIN_HOURS_SINCE_INBOUND_REPLY = 24  # don't send email within 24h of a prospect reply
DEFAULT_MIN_HOURS_SINCE_OUTBOUND_EMAIL = 48  # don't call within 48h of an outbound email
DEFAULT_MIN_HOURS_SINCE_LAST_CALL = 48  # don't call the same prospect twice within 48h


def can_send_email(
    prospect,
    min_hours_since_inbound: int = DEFAULT_MIN_HOURS_SINCE_INBOUND_REPLY,
    min_hours_since_call: int = DEFAULT_MIN_HOURS_SINCE_LAST_CALL,
) -> Tuple[bool, str]:
    """Return (allowed, reason) for whether we should send this prospect an email.

    Rules:
      1. If they replied in the last N hours, skip — the reply handler should
         respond to them, not the sequence cron.
      2. If we called them in the last M hours, skip — feels robotic to email
         the same day as a call.
    """
    if not prospect:
        return False, 'no prospect'

    state = get_conversation_state(prospect)
    now = timezone.now()

    if state.last_inbound_at:
        gap = now - state.last_inbound_at
        if gap < timedelta(hours=min_hours_since_inbound):
            hours = gap.total_seconds() / 3600
            return False, (
                f'prospect replied {hours:.1f}h ago '
                f'(min gap {min_hours_since_inbound}h) — reply handler will respond'
            )

    if state.last_call_at:
        gap = now - state.last_call_at
        if gap < timedelta(hours=min_hours_since_call):
            hours = gap.total_seconds() / 3600
            return False, (
                f'called prospect {hours:.1f}h ago '
                f'(min gap {min_hours_since_call}h) — let the call breathe'
            )

    return True, 'ok'


def can_place_call(
    prospect,
    min_hours_since_email: int = DEFAULT_MIN_HOURS_SINCE_OUTBOUND_EMAIL,
    min_hours_since_inbound: int = DEFAULT_MIN_HOURS_SINCE_INBOUND_REPLY,
    min_hours_since_last_call: int = DEFAULT_MIN_HOURS_SINCE_LAST_CALL,
) -> Tuple[bool, str]:
    """Return (allowed, reason) for whether we should call this prospect.

    Rules:
      1. If they replied in the last N hours, skip — answer the reply first.
      2. If we sent them an email in the last M hours, skip — give the email
         time to land before calling about it.
      3. If we already called them in the last K hours, skip — don't spam.
    """
    if not prospect:
        return False, 'no prospect'

    state = get_conversation_state(prospect)
    now = timezone.now()

    if state.last_inbound_at:
        gap = now - state.last_inbound_at
        if gap < timedelta(hours=min_hours_since_inbound):
            hours = gap.total_seconds() / 3600
            return False, (
                f'prospect replied {hours:.1f}h ago '
                f'(min gap {min_hours_since_inbound}h) — handle reply first'
            )

    if state.last_outbound_at:
        gap = now - state.last_outbound_at
        if gap < timedelta(hours=min_hours_since_email):
            hours = gap.total_seconds() / 3600
            return False, (
                f'emailed prospect {hours:.1f}h ago '
                f'(min gap {min_hours_since_email}h) — give the email time to land'
            )

    if state.last_call_at:
        gap = now - state.last_call_at
        if gap < timedelta(hours=min_hours_since_last_call):
            hours = gap.total_seconds() / 3600
            return False, (
                f'called prospect {hours:.1f}h ago '
                f'(min gap {min_hours_since_last_call}h) — not repeating so soon'
            )

    return True, 'ok'


# ---------------------------------------------------------------------------
# next_call_window — schedules a future call so it lands in business hours
# ---------------------------------------------------------------------------

DEFAULT_CALL_WINDOW_TZ = 'Europe/Dublin'
DEFAULT_CALL_WINDOW_START_HOUR = 9   # 09:00 prospect-local
DEFAULT_CALL_WINDOW_END_HOUR = 18    # 18:00 prospect-local
DEFAULT_CALL_WINDOW_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon-Fri (Mon=0)


def next_call_window(prospect, *, now=None) -> 'datetime.datetime':
    """Return the earliest UTC datetime when a call to `prospect` may dispatch.

    Rules (in order):
      1. Respect the email→call cooldown from `can_place_call` — if a call
         right now would be blocked by 48h-since-email, push to that floor.
      2. Snap to prospect-local business hours. Default 09:00-18:00 Mon-Fri,
         in `Campaign.send_window_timezone` (default Europe/Dublin).
      3. Never schedule in the past — the caller can dispatch immediately if
         the returned datetime is now-ish.

    Returned value is a tz-aware UTC datetime.
    """
    from datetime import datetime, time as dtime
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # py < 3.9 — should not happen on this stack
        from backports.zoneinfo import ZoneInfo  # type: ignore

    now = now or timezone.now()

    # Step 1: floor at email-cooldown if applicable.
    floor = now
    state = get_conversation_state(prospect)
    if state.last_outbound_at:
        cooldown = state.last_outbound_at + timedelta(
            hours=DEFAULT_MIN_HOURS_SINCE_OUTBOUND_EMAIL
        )
        if cooldown > floor:
            floor = cooldown
    if state.last_call_at:
        cooldown = state.last_call_at + timedelta(
            hours=DEFAULT_MIN_HOURS_SINCE_LAST_CALL
        )
        if cooldown > floor:
            floor = cooldown

    # Step 2: resolve prospect's local timezone (via campaign).
    tz_name = DEFAULT_CALL_WINDOW_TZ
    campaign = getattr(prospect, 'campaign', None)
    if campaign is not None:
        tz_name = (
            getattr(campaign, 'send_window_timezone', '') or DEFAULT_CALL_WINDOW_TZ
        )
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_CALL_WINDOW_TZ)

    # Convert floor to prospect-local time.
    local = floor.astimezone(tz)
    local = _snap_to_business_hours(local)

    # Convert back to UTC.
    return local.astimezone(timezone.utc) if hasattr(timezone, 'utc') else local


def _snap_to_business_hours(dt):
    """Move `dt` (tz-aware) forward to the next business-hour slot.

    Iterates day-by-day for at most 14 days (defensive cap) until landing on
    a Mon-Fri inside [09:00, 18:00).
    """
    from datetime import datetime, time as dtime
    cap = 14
    while cap > 0:
        cap -= 1
        weekday = dt.weekday()
        if weekday not in DEFAULT_CALL_WINDOW_WEEKDAYS:
            # Roll forward to 09:00 next weekday.
            days_ahead = 1
            while (dt.weekday() + days_ahead) % 7 not in DEFAULT_CALL_WINDOW_WEEKDAYS:
                days_ahead += 1
            dt = (dt + timedelta(days=days_ahead)).replace(
                hour=DEFAULT_CALL_WINDOW_START_HOUR, minute=0, second=0, microsecond=0,
            )
            continue
        if dt.hour < DEFAULT_CALL_WINDOW_START_HOUR:
            dt = dt.replace(
                hour=DEFAULT_CALL_WINDOW_START_HOUR, minute=0, second=0, microsecond=0,
            )
            continue
        if dt.hour >= DEFAULT_CALL_WINDOW_END_HOUR:
            # Past close — snap to 09:00 next day.
            dt = (dt + timedelta(days=1)).replace(
                hour=DEFAULT_CALL_WINDOW_START_HOUR, minute=0, second=0, microsecond=0,
            )
            continue
        return dt
    return dt
