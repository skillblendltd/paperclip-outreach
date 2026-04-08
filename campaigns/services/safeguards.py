"""
Rate limiting and safety checks for email sending.
Consolidated from views.py and process_queue.py safeguard logic.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from campaigns.models import Campaign, Prospect, EmailLog, Suppression
from campaigns.services.eligibility import is_suppressed


def daily_remaining(campaign):
    """How many more emails can this campaign send today."""
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = EmailLog.objects.filter(
        campaign=campaign, created_at__gte=today_start, status='sent'
    ).count()
    return max(0, campaign.max_emails_per_day - sent_today)


def check_min_gap(campaign):
    """Return (ok, wait_seconds). True if enough time has passed since last send."""
    last_sent = EmailLog.objects.filter(
        campaign=campaign, status='sent'
    ).order_by('-created_at').first()
    if not last_sent:
        return True, 0
    gap = timezone.now() - last_sent.created_at
    min_gap = timedelta(minutes=campaign.min_gap_minutes)
    if gap >= min_gap:
        return True, 0
    return False, int((min_gap - gap).total_seconds())


def can_send_to_prospect(campaign, prospect, sequence_number):
    """
    All prospect-level checks before sending.
    Returns (ok: bool, reason: str).
    """
    # Send enabled
    if not prospect.send_enabled:
        return False, f'Sending disabled for {prospect.business_name}'

    # Status check
    if prospect.status in ('not_interested', 'opted_out'):
        return False, f'Prospect status is {prospect.status}'

    # Follow-up only for contacted
    if sequence_number > 1 and prospect.status != 'contacted':
        return False, f'Follow-up only for contacted (current: {prospect.status})'

    # Has email
    if not prospect.email:
        return False, f'No email for {prospect.business_name}'

    # Suppression
    product = campaign.product_ref
    if is_suppressed(prospect.email, product):
        return False, f'{prospect.email} is suppressed'

    # Max per prospect
    prospect_sent = EmailLog.objects.filter(prospect=prospect, status='sent').count()
    if prospect_sent >= campaign.max_emails_per_prospect:
        return False, f'Max emails reached ({prospect_sent}/{campaign.max_emails_per_prospect})'

    # Sequence order
    if campaign.require_sequence_order and sequence_number > 1:
        prev_exists = EmailLog.objects.filter(
            prospect=prospect, sequence_number=sequence_number - 1, status='sent'
        ).exists()
        if not prev_exists:
            return False, f'Sequence {sequence_number - 1} not sent yet'

    # Duplicate check
    if EmailLog.objects.filter(
        prospect=prospect, sequence_number=sequence_number, status='sent'
    ).exists():
        return False, f'Sequence {sequence_number} already sent'

    return True, ''
