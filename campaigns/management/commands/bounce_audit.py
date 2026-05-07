"""
Daily bounce-rate health check for sending domains.

Reports:
    - Bounce rate per sending domain (last 7 days)
    - Complaint rate per sending domain (last 7 days)
    - Stale data: Prospects send_enabled=True but with bounce/complaint history

Alerts (logged at WARNING level so they show in cron logs):
    - Bounce rate > 5%   (AWS suspension threshold)
    - Complaint rate > 0.1%  (FBL threshold)

Run daily from cron: 0 8 * * * python manage.py bounce_audit
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from campaigns.models import EmailLog, Suppression, Prospect


logger = logging.getLogger(__name__)


WINDOW_DAYS = 7
BOUNCE_RATE_THRESHOLD = 0.05      # 5% — AWS suspension threshold
COMPLAINT_RATE_THRESHOLD = 0.001  # 0.1% — FBL threshold


class Command(BaseCommand):
    help = 'Audit bounce/complaint rates per sending domain and surface stale prospects.'

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=WINDOW_DAYS)

        self.stdout.write('=' * 60)
        self.stdout.write(f'Bounce Audit — last {WINDOW_DAYS} days (since {since:%Y-%m-%d})')
        self.stdout.write('=' * 60)

        # ----- Per-sending-domain bounce stats -----
        # We use Suppression.notes containing 'sending_domain=X' as the linkage
        # (process_ses_bounces records the domain in notes).
        bounces_by_domain = defaultdict(int)
        complaints_by_domain = defaultdict(int)

        recent_suppressions = Suppression.objects.filter(
            created_at__gte=since,
            reason__in=['bounce', 'complaint'],
        )
        for sup in recent_suppressions:
            domain = self._extract_domain_from_notes(sup.notes or '')
            if not domain:
                domain = 'unknown'
            if sup.reason == 'bounce':
                bounces_by_domain[domain] += 1
            elif sup.reason == 'complaint':
                complaints_by_domain[domain] += 1

        # Sends per sending domain (derived from EmailLog → campaign.from_email)
        sends_by_domain = defaultdict(int)
        for el in EmailLog.objects.filter(
            created_at__gte=since,
            status='sent',
        ).select_related('campaign'):
            from_email = (el.campaign.from_email if el.campaign else '') or ''
            domain = from_email.split('@', 1)[1].lower().strip() if '@' in from_email else 'unknown'
            sends_by_domain[domain] += 1

        all_domains = set(sends_by_domain) | set(bounces_by_domain) | set(complaints_by_domain)

        if not all_domains:
            self.stdout.write('No sends or bounces in window.')
            return

        self.stdout.write('')
        self.stdout.write(
            f'{"Domain":<28} {"Sent":>7} {"Bounce":>7} {"Bnc%":>7} {"Cmplt":>6} {"Cmp%":>7}'
        )
        self.stdout.write('-' * 68)

        any_alert = False
        for domain in sorted(all_domains):
            sent = sends_by_domain.get(domain, 0)
            bn = bounces_by_domain.get(domain, 0)
            cn = complaints_by_domain.get(domain, 0)
            bn_rate = (bn / sent) if sent else 0
            cn_rate = (cn / sent) if sent else 0
            self.stdout.write(
                f'{domain[:28]:<28} {sent:>7} {bn:>7} {bn_rate*100:>6.2f}% {cn:>6} {cn_rate*100:>6.3f}%'
            )

            # Alerts
            if sent >= 100 and bn_rate > BOUNCE_RATE_THRESHOLD:
                logger.warning(
                    'HIGH BOUNCE RATE: domain=%s sent=%d bounces=%d rate=%.2f%% (threshold=%.0f%%)',
                    domain, sent, bn, bn_rate * 100, BOUNCE_RATE_THRESHOLD * 100
                )
                any_alert = True
            if sent >= 100 and cn_rate > COMPLAINT_RATE_THRESHOLD:
                logger.warning(
                    'HIGH COMPLAINT RATE: domain=%s sent=%d complaints=%d rate=%.3f%% (threshold=%.1f%%)',
                    domain, sent, cn, cn_rate * 100, COMPLAINT_RATE_THRESHOLD * 100
                )
                any_alert = True

        # ----- Data integrity check: prospects send_enabled but bouncer history -----
        self.stdout.write('')
        self.stdout.write('Data integrity:')
        bounce_emails_set = set(
            Suppression.objects.filter(reason__in=['bounce', 'complaint'])
            .values_list('email', flat=True)
        )
        leak_count = Prospect.objects.filter(
            email__in=bounce_emails_set,
            send_enabled=True,
        ).count()
        if leak_count:
            logger.warning(
                'DATA INTEGRITY: %d Prospects still send_enabled=True despite bounce/complaint suppression',
                leak_count
            )
            self.stdout.write(self.style.ERROR(
                f'  ⚠ {leak_count} Prospects still send_enabled=True with bounce history (run Phase 1 backfill)'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ No Prospects send_enabled with bounce/complaint history'))

        # ----- Suppression total counts -----
        self.stdout.write('')
        self.stdout.write('Suppression totals (all time):')
        from collections import Counter
        for reason, count in Counter(Suppression.objects.values_list('reason', flat=True)).most_common():
            self.stdout.write(f'  {reason:<15} {count}')

        if any_alert:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('⚠ ALERTS triggered — see WARNING lines above'))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✓ All sending domains within thresholds'))

    # ------------------------------------------------------------------
    def _extract_domain_from_notes(self, notes):
        """Pull sending_domain=X.com from Suppression.notes if present."""
        if not notes or 'sending_domain=' not in notes:
            return ''
        try:
            after = notes.split('sending_domain=', 1)[1]
            domain = after.split(',', 1)[0].split(')', 1)[0].split(' ', 1)[0]
            return domain.strip().lower()
        except Exception:
            return ''
