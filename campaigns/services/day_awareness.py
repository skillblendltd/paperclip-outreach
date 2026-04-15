"""Date-of-day awareness block for reply prompts.

Bug fix 2026-04-15: Lisa replied on a Wednesday and suggested "Tuesday or
Wednesday morning" because her voice rules contained hardcoded example
lines referencing those days. Personas copy the examples verbatim. The
fix is two-sided:

  1. This module injects a fresh "today is <day>, <date>" block into the
     preamble on every run, with a hard rule that any proposed slot must
     be strictly after today.
  2. Voice rules in `PromptTemplate.system_prompt` are cleaned of
     hardcoded weekday names and point at this block instead.

Safe to inject into non-cached layers (kicker in `cacheable_preamble`,
inline in `handle_replies._build_execution_preamble`). Must NOT live in
the cacheable stable prefix — it changes daily and would invalidate the
5-minute Anthropic prompt cache for no benefit.
"""
from datetime import datetime
from zoneinfo import ZoneInfo


def current_day_awareness_block(timezone: str = 'Europe/Dublin') -> str:
    """Return a preamble block stating today's date + day of week + a
    hard rule about only proposing future slots.

    Args:
        timezone: IANA timezone for the persona. Defaults to Dublin because
            Lisa is the persona where this bug surfaced. TaggIQ/FP Franchise
            personas also live in Europe/Dublin so the default is safe for
            the whole project today. Pass a different zone when a new
            persona in another region lands.

    Returns:
        Formatted text block ready to concatenate into a prompt. Regenerated
        on every call so the date is always current.
    """
    now = datetime.now(ZoneInfo(timezone))
    day_name = now.strftime('%A')
    date_str = now.strftime('%d %B %Y')
    weekday = now.weekday()  # Mon=0 ... Sun=6

    if weekday == 4:  # Friday
        suggestion_hint = (
            'Today is Friday. Propose "Monday or Tuesday next week" as the '
            'default slot pair. Do not suggest any day this week.'
        )
    elif weekday == 5:  # Saturday
        suggestion_hint = (
            'Today is Saturday. Propose "Monday or Tuesday" as the default '
            'slot pair. Do not reference this weekend.'
        )
    elif weekday == 6:  # Sunday
        suggestion_hint = (
            'Today is Sunday. Propose "Monday or Tuesday" as the default '
            'slot pair. Do not reference today.'
        )
    else:
        # Mon=0, Tue=1, Wed=2, Thu=3 -> offer next two weekdays
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        next1 = days[(weekday + 1) % 5] if weekday < 4 else 'Monday'
        next2 = days[(weekday + 2) % 5] if weekday < 3 else days[(weekday + 2) % 5] if weekday == 3 else 'Tuesday'
        # Simpler: compute two strictly-after weekdays.
        idx1 = weekday + 1
        idx2 = weekday + 2
        if idx1 >= 5:
            idx1 = 0  # wrap to Monday
        if idx2 >= 5:
            idx2 = idx2 - 5
        next1 = days[idx1]
        next2 = days[idx2]
        suggestion_hint = (
            f'Today is {day_name}. Propose "{next1} or {next2}" as the '
            f'default slot pair, or "later this week" if both are later '
            f'today. Never propose {day_name} itself as a slot in this '
            f'reply - the prospect will read this email hours from now '
            f'and the window may have closed.'
        )

    return (
        '==============================================================\n'
        'CURRENT DATE AWARENESS (regenerated every run)\n'
        '==============================================================\n'
        f'\n'
        f'Today is {day_name}, {date_str} ({timezone}).\n'
        f'\n'
        f'HARD RULE: When proposing call, meeting, or visit slots, ONLY\n'
        f'suggest days strictly AFTER today. A slot that has already\n'
        f'passed or is happening right now is not a slot - it is a\n'
        f'confused email. If your voice rules below show example lines\n'
        f'with specific weekday names (e.g. "Tuesday or Wednesday"), treat\n'
        f'those names as placeholders. Replace them with the correct\n'
        f'forward-looking weekdays for today.\n'
        f'\n'
        f'{suggestion_hint}\n'
        f'\n'
        f'Prefer concrete weekday names over relative phrasing. "This\n'
        f'week" and "next week" are ambiguous near weekends; "{day_name} +\n'
        f'N" is not. Use the hint above unless the inbound itself pins\n'
        f'down a different preferred day.\n'
        f'\n'
    )
