"""
Per-org AI budget ceiling service.

**AI ARCHITECT REQUIREMENT:** Every new AI call path must consult this service
BEFORE invoking a model. When an Organization is at or over its monthly budget,
new AI calls must either:
  - Block entirely (hard fail), or
  - Degrade gracefully to flat templates (soft fail)

This is the fail-safe against runaway loops billing $10K before anyone notices.

**Phase 2A status:** Library exists. Not yet wired into handle_replies or any
live AI path. That's Phase 2B. Phase 2A just builds the plumbing so it's ready.

Usage:
    from campaigns.services.ai_budget import (
        check_budget_before_call, record_cost, get_usage_summary,
    )

    allowed, reason = check_budget_before_call(org)
    if not allowed:
        logger.warning(f'AI budget exceeded for {org}: {reason}')
        return DEGRADE_TO_FLAT_TEMPLATE

    # ... make the AI call ...

    # After the call, record what it cost
    record_cost(org, cents=17)  # 17 cents for this Sonnet reply

    # For dashboards / alerts:
    usage = get_usage_summary(org)  # returns dict with budget, used, remaining, pct
"""
from datetime import date
from decimal import Decimal
from typing import Tuple, Dict

from django.db import transaction
from django.utils import timezone


# Warn threshold — log a warning at 80% of budget consumed.
WARN_THRESHOLD_PCT = 80


def check_budget_before_call(organization) -> Tuple[bool, str]:
    """Return (allowed, reason) for whether this org can make another AI call.

    Rules:
      1. If budget is zero or unset, allow (org hasn't configured limits).
      2. If current month anchor is missing or stale (>30 days old), reset
         the counter first, then check.
      3. If used < budget, allow.
      4. If used >= budget, deny.

    Side effects: may reset ai_usage_current_month_cents if the month rolled.
    """
    if not organization:
        return False, 'no organization'

    # Check if monthly counter needs reset
    _maybe_reset_month(organization)

    budget_cents = int(Decimal(organization.ai_budget_usd_monthly) * 100)
    if budget_cents <= 0:
        return True, 'no budget configured (unlimited)'

    used_cents = organization.ai_usage_current_month_cents or 0
    if used_cents >= budget_cents:
        return False, (
            f'monthly budget exceeded: '
            f'${used_cents / 100:.2f} used of ${budget_cents / 100:.2f}'
        )

    # Warn at 80%
    pct = (used_cents / budget_cents) * 100
    if pct >= WARN_THRESHOLD_PCT:
        return True, f'WARN: {pct:.1f}% of budget used'

    return True, 'ok'


def record_cost(organization, cents: int) -> None:
    """Atomically increment the org's AI usage counter.

    Uses F() expression for safe concurrent updates. No race conditions.
    """
    if not organization or cents <= 0:
        return
    from django.db.models import F
    type(organization).objects.filter(pk=organization.pk).update(
        ai_usage_current_month_cents=F('ai_usage_current_month_cents') + cents,
        updated_at=timezone.now(),
    )


def get_usage_summary(organization) -> Dict:
    """Return a dict with budget/used/remaining/pct for dashboards.

    Re-fetches the org to get the fresh counter (avoid stale-read issues).
    """
    if not organization:
        return {}
    fresh = type(organization).objects.get(pk=organization.pk)
    budget_cents = int(Decimal(fresh.ai_budget_usd_monthly) * 100)
    used_cents = fresh.ai_usage_current_month_cents or 0
    remaining_cents = max(0, budget_cents - used_cents)
    pct = (used_cents / budget_cents * 100) if budget_cents > 0 else 0.0
    return {
        'budget_usd': float(fresh.ai_budget_usd_monthly),
        'used_usd': used_cents / 100,
        'remaining_usd': remaining_cents / 100,
        'pct_used': round(pct, 1),
        'month_anchor': fresh.ai_usage_month_anchor,
        'over_budget': used_cents >= budget_cents if budget_cents > 0 else False,
    }


# ---------- internal ----------

def _maybe_reset_month(organization) -> None:
    """Reset ai_usage_current_month_cents if the month has rolled over.

    Anchor logic: if the anchor is missing, set it to today. If today is in
    a different calendar month than the anchor, reset counter and update anchor.
    """
    today = date.today()
    anchor = organization.ai_usage_month_anchor

    if anchor is None:
        # First time — set anchor, don't reset (counter is already 0 at org creation)
        type(organization).objects.filter(pk=organization.pk).update(
            ai_usage_month_anchor=today.replace(day=1),
            updated_at=timezone.now(),
        )
        organization.ai_usage_month_anchor = today.replace(day=1)
        return

    if today.year != anchor.year or today.month != anchor.month:
        # Month rolled over — reset
        with transaction.atomic():
            type(organization).objects.filter(pk=organization.pk).update(
                ai_usage_current_month_cents=0,
                ai_usage_month_anchor=today.replace(day=1),
                updated_at=timezone.now(),
            )
        organization.ai_usage_current_month_cents = 0
        organization.ai_usage_month_anchor = today.replace(day=1)
