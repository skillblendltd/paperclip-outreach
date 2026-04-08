"""
Prospect eligibility for sequence emails.
Consolidated from bni send_sequence.py, google-maps send_ireland_sequences.py, fp send_campaign.py.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from campaigns.models import Prospect, Suppression, EmailLog

# Statuses that should NEVER receive sequence emails
TERMINAL_STATUSES = frozenset([
    'opted_out', 'not_interested', 'interested', 'engaged',
    'demo_scheduled', 'design_partner',
])

MIN_GAP_DAYS = 7


def get_eligible_prospects(campaign):
    """
    Return list of (Prospect, next_sequence_number) tuples for prospects
    ready to receive their next email in this campaign.

    Rules (include-based):
      Seq 1: status='new', emails_sent=0, has email, send_enabled, not suppressed
      Seq 2-5: status='contacted', emails_sent=seq-1, 7-day gap, send_enabled, not suppressed
    """
    results = []

    base_qs = Prospect.objects.filter(
        campaign=campaign,
        send_enabled=True,
    ).exclude(
        Q(email='') | Q(email__isnull=True)
    ).exclude(
        status__in=TERMINAL_STATUSES
    )

    product = campaign.product_ref

    # Seq 1: new prospects with no emails sent
    seq1 = base_qs.filter(status='new', emails_sent=0)
    for p in seq1:
        if not is_suppressed(p.email, product):
            results.append((p, 1))

    # Seq 2-5: contacted prospects with correct email count and gap met
    gap_cutoff = timezone.now() - timedelta(days=MIN_GAP_DAYS)
    contacted = base_qs.filter(status='contacted')

    for p in contacted:
        if p.emails_sent < 1 or p.emails_sent > 4:
            continue
        next_seq = p.emails_sent + 1
        # Check gap
        if p.last_emailed_at and p.last_emailed_at > gap_cutoff:
            continue
        # Check not already sent this sequence
        already_sent = EmailLog.objects.filter(
            prospect=p, sequence_number=next_seq, status='sent'
        ).exists()
        if already_sent:
            continue
        if not is_suppressed(p.email, product):
            results.append((p, next_seq))

    return results


def is_suppressed(email, product):
    """
    Check suppression list with product scoping.
    Suppressed if: (email match) AND (product is NULL/global OR product matches).
    """
    if not email:
        return False
    qs = Suppression.objects.filter(email__iexact=email)
    if product:
        return qs.filter(Q(product__isnull=True) | Q(product=product)).exists()
    return qs.filter(product__isnull=True).exists()
