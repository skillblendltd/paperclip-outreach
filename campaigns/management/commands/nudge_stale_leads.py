"""
Nudge warm leads that have gone quiet, and reactivate follow_up_later prospects.

Runs daily Mon-Fri at 11:30am (after send_sequences at 11am).

Rules:
  1. interested/engaged, last_emailed_at > 14 days ago  -> transition to follow_up_later
  2. interested/engaged, last_emailed_at 7-14 days ago  -> queue warm_nudge email
  3. follow_up_later, follow_up_after <= today           -> reactivate to contacted

Usage:
    python manage.py nudge_stale_leads            # live run
    python manage.py nudge_stale_leads --dry-run  # preview only
    python manage.py nudge_stale_leads --product taggiq  # one product
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.models import Prospect
from campaigns.services import lifecycle

logger = logging.getLogger(__name__)

WARM_STATES = ['interested', 'engaged']
SEVEN_DAYS = timedelta(days=7)
FOURTEEN_DAYS = timedelta(days=14)


class Command(BaseCommand):
    help = 'Nudge stale warm leads and reactivate follow_up_later prospects'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview only, no changes')
        parser.add_argument('--product', type=str, help='Product slug filter (e.g. taggiq)')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        product_slug = options.get('product')
        now = timezone.now()

        if dry_run:
            self.stdout.write('[DRY RUN] No changes will be made.')

        qs = Prospect.objects.filter(send_enabled=True)
        if product_slug:
            qs = qs.filter(campaign__product_ref__slug=product_slug)

        moved_to_later = 0
        queued_nudge = 0
        reactivated = 0

        from campaigns.services.conversation import get_conversation_state

        def _last_outbound(prospect):
            """Return the most recent outbound touch datetime (email OR AI reply),
            using ConversationState so AI replies are counted, not just send_sequences."""
            state = get_conversation_state(prospect)
            return state.last_outbound_at

        # ----------------------------------------------------------------
        # Rule 1: Move 14-day stale warm leads to follow_up_later
        # ----------------------------------------------------------------
        # Pre-filter on last_emailed_at for DB efficiency, then refine
        # with conversation state to avoid false positives on AI-replied threads.
        stale_14_candidates = qs.filter(
            status__in=WARM_STATES,
            last_emailed_at__lte=now - FOURTEEN_DAYS,
        )
        stale_14 = [
            p for p in stale_14_candidates
            if not _last_outbound(p) or _last_outbound(p) <= now - FOURTEEN_DAYS
        ]
        self.stdout.write(f'\n[14-day stale] {len(stale_14)} prospects eligible (of {stale_14_candidates.count()} candidates)')

        for p in stale_14:
            last_touch = _last_outbound(p)
            last_str = last_touch.strftime('%Y-%m-%d') if last_touch else 'never'
            self.stdout.write(
                f'  {p.email} ({p.business_name}) | status={p.status} | last_touch={last_str}'
            )
            if not dry_run:
                try:
                    lifecycle.transition(
                        p, 'follow_up_later',
                        reason='nudge:14d_no_activity',
                        triggered_by='nudge_stale_leads',
                    )
                    moved_to_later += 1
                    self.stdout.write(self.style.WARNING(f'  -> follow_up_later'))
                except ValueError as exc:
                    self.stdout.write(f'  skip: {exc}')
            else:
                self.stdout.write(f'  [DRY RUN] -> would move to follow_up_later')
                moved_to_later += 1

        # ----------------------------------------------------------------
        # Rule 2: Queue nudge email for 7-14 day stale warm leads
        # ----------------------------------------------------------------
        stale_7_candidates = qs.filter(
            status__in=WARM_STATES,
            last_emailed_at__lte=now - SEVEN_DAYS,
            last_emailed_at__gt=now - FOURTEEN_DAYS,
        )
        stale_7 = [
            p for p in stale_7_candidates
            if not _last_outbound(p) or (
                now - FOURTEEN_DAYS < _last_outbound(p) <= now - SEVEN_DAYS
            )
        ]
        self.stdout.write(f'\n[7-day nudge] {len(stale_7)} prospects eligible')

        for p in stale_7:
            last_touch = _last_outbound(p)
            last_str = last_touch.strftime('%Y-%m-%d') if last_touch else 'never'
            self.stdout.write(
                f'  {p.email} ({p.business_name}) | status={p.status} | last_touch={last_str}'
            )
            if not dry_run:
                try:
                    from campaigns.services.lifecycle import _queue_email
                    _queue_email(p, template='warm_nudge',
                                 delay_hours=0, triggered_by='nudge_stale_leads')
                    queued_nudge += 1
                    self.stdout.write(f'  -> queued warm_nudge email')
                except Exception as exc:
                    self.stdout.write(f'  skip: {exc}')
            else:
                self.stdout.write(f'  [DRY RUN] -> would queue warm_nudge email')
                queued_nudge += 1

        # ----------------------------------------------------------------
        # Rule 3: Reactivate follow_up_later whose date has passed
        # ----------------------------------------------------------------
        reactivate_qs = qs.filter(
            status='follow_up_later',
            follow_up_after__lte=now,
        )
        self.stdout.write(f'\n[reactivate] {reactivate_qs.count()} follow_up_later ready')

        for p in reactivate_qs:
            fa_str = p.follow_up_after.strftime('%Y-%m-%d') if p.follow_up_after else 'unset'
            self.stdout.write(
                f'  {p.email} ({p.business_name}) | follow_up_after={fa_str}'
            )
            if not dry_run:
                try:
                    lifecycle.transition(
                        p, 'contacted',
                        reason='reactivate:follow_up_after_passed',
                        triggered_by='nudge_stale_leads',
                    )
                    # Reset to emails_sent=1 so they receive seq 2+ (not seq 1 again)
                    if p.emails_sent == 0:
                        p.emails_sent = 1
                        p.save(update_fields=['emails_sent', 'updated_at'])
                    reactivated += 1
                    self.stdout.write(self.style.SUCCESS(f'  -> reactivated (contacted)'))
                except ValueError as exc:
                    self.stdout.write(f'  skip: {exc}')
            else:
                self.stdout.write(f'  [DRY RUN] -> would reactivate to contacted')
                reactivated += 1

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        self.stdout.write(f'\n--- nudge_stale_leads summary ---')
        self.stdout.write(f'Moved to follow_up_later: {moved_to_later}')
        self.stdout.write(f'Nudge emails queued:      {queued_nudge}')
        self.stdout.write(f'Reactivated:              {reactivated}')
        if dry_run:
            self.stdout.write('[DRY RUN] No changes applied.')
