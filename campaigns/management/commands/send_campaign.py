"""
Management command to send outreach emails for a campaign.

Usage:
    python manage.py send_campaign --campaign "TaggIQ Launch" --dry-run
    python manage.py send_campaign --campaign "TaggIQ Launch" --limit 10
    python manage.py send_campaign --campaign "TaggIQ Launch" --tier A --limit 5
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q

from campaigns.models import Campaign, Prospect, EmailLog, Suppression
from campaigns.email_service import EmailService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send next sequence email to eligible prospects in a campaign'

    def add_arguments(self, parser):
        parser.add_argument('--campaign', required=True, help='Campaign name')
        parser.add_argument('--dry-run', action='store_true', help='Preview without sending')
        parser.add_argument('--limit', type=int, default=0, help='Max emails to send (0=use daily limit)')
        parser.add_argument('--tier', help='Only send to this tier (A/B/C/D)')
        parser.add_argument('--segment', help='Only send to this segment')
        parser.add_argument('--sequence', type=int, default=0, help='Send specific sequence number')

    def _ab_variant(self, prospect):
        return 'A' if hash(str(prospect.id)) % 2 == 0 else 'B'

    def handle(self, *args, **options):
        campaign_name = options['campaign']
        dry_run = options['dry_run']
        limit = options['limit']
        tier_filter = options.get('tier')
        segment_filter = options.get('segment')
        seq_override = options.get('sequence', 0)

        # Find campaign
        try:
            campaign = Campaign.objects.get(name__icontains=campaign_name)
        except Campaign.DoesNotExist:
            raise CommandError(f'Campaign "{campaign_name}" not found.')
        except Campaign.MultipleObjectsReturned:
            raise CommandError(f'Multiple campaigns match "{campaign_name}". Be more specific.')

        self.stdout.write(f'\nCampaign: {campaign.name} [{campaign.product}]')
        self.stdout.write(f'From: {campaign.from_name} <{campaign.from_email}>')
        self.stdout.write(f'Sending: {"ENABLED" if campaign.sending_enabled else "DISABLED"}')

        if not campaign.sending_enabled and not dry_run:
            raise CommandError('Sending is DISABLED for this campaign. Enable in admin first.')

        # Check daily usage
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = EmailLog.objects.filter(
            campaign=campaign, created_at__gte=today_start, status='sent'
        ).count()
        remaining = campaign.max_emails_per_day - sent_today
        self.stdout.write(f'Sent today: {sent_today}/{campaign.max_emails_per_day} (remaining: {remaining})')

        if remaining <= 0 and not dry_run:
            raise CommandError('Daily limit reached.')

        effective_limit = limit if limit > 0 else remaining
        if not dry_run:
            effective_limit = min(effective_limit, remaining)

        # Get eligible prospects
        suppressed_emails = set(Suppression.objects.values_list('email', flat=True))

        # Seq 1 goes to 'new', Seq 2+ goes to 'contacted' only
        # Never use exclude-based filtering — interested/demo_scheduled/engaged
        # get personalized replies, not automated sequences
        if seq_override == 1 or seq_override == 0:
            allowed_statuses = ['new', 'contacted']
        else:
            allowed_statuses = ['contacted']

        qs = Prospect.objects.filter(
            campaign=campaign,
            send_enabled=True,
            status__in=allowed_statuses,
        ).exclude(
            Q(email='') | Q(email__isnull=True)
        )

        if tier_filter:
            qs = qs.filter(tier=tier_filter)
        if segment_filter:
            qs = qs.filter(segment=segment_filter)

        prospects = list(qs.order_by('-score'))

        # Filter: not suppressed, not maxed out, has next sequence to send
        eligible = []
        for p in prospects:
            if p.email.lower() in {e.lower() for e in suppressed_emails}:
                continue

            sent_count = EmailLog.objects.filter(prospect=p, status='sent').count()
            if sent_count >= campaign.max_emails_per_prospect:
                continue

            # Determine next sequence number
            if seq_override > 0:
                next_seq = seq_override
            else:
                last_seq = EmailLog.objects.filter(
                    prospect=p, status='sent'
                ).order_by('-sequence_number').values_list('sequence_number', flat=True).first()
                next_seq = (last_seq or 0) + 1

            # Check sequence order
            if campaign.require_sequence_order and next_seq > 1:
                prev_exists = EmailLog.objects.filter(
                    prospect=p, sequence_number=next_seq - 1, status='sent'
                ).exists()
                if not prev_exists:
                    continue

            # Check not already sent this sequence
            if EmailLog.objects.filter(prospect=p, sequence_number=next_seq, status='sent').exists():
                continue

            eligible.append((p, next_seq))

        self.stdout.write(f'Eligible prospects: {len(eligible)}')
        self.stdout.write(f'Will {"preview" if dry_run else "send"}: {min(len(eligible), effective_limit)}\n')

        sent = 0
        for prospect, seq_num in eligible[:effective_limit]:
            variant = self._ab_variant(prospect)
            line = (
                f'  {"[DRY RUN] " if dry_run else ""}'
                f'seq={seq_num} variant={variant} '
                f'{prospect.business_name} <{prospect.email}> '
                f'(tier={prospect.tier} score={prospect.score})'
            )

            if dry_run:
                self.stdout.write(self.style.WARNING(line))
                sent += 1
                continue

            # Check min gap
            last_sent = EmailLog.objects.filter(
                campaign=campaign, status='sent'
            ).order_by('-created_at').first()
            if last_sent:
                gap = timezone.now() - last_sent.created_at
                min_gap = timedelta(minutes=campaign.min_gap_minutes)
                if gap < min_gap:
                    wait = int((min_gap - gap).total_seconds())
                    self.stdout.write(self.style.WARNING(
                        f'  Min gap not met. Need to wait {wait}s. Stopping.'
                    ))
                    break

            # Build email (placeholder subject/body - agents provide real content)
            subject = f'Follow-up from {campaign.from_name or campaign.name}'
            body_html = f'<p>Hi {prospect.decision_maker_name.split()[0] if prospect.decision_maker_name else "there"},</p>'

            variables = {
                'FNAME': prospect.decision_maker_name.split()[0] if prospect.decision_maker_name else 'there',
                'COMPANY': prospect.business_name,
                'CITY': prospect.city,
                'SEGMENT': prospect.get_segment_display() if prospect.segment else prospect.business_type,
            }

            rendered_subject = EmailService.render_template(subject, variables)
            rendered_body = EmailService.render_template(body_html, variables)
            rendered_body += campaign.unsubscribe_footer_html

            try:
                result = EmailService.send_email(
                    to_emails=[prospect.email],
                    subject=rendered_subject,
                    body_html=rendered_body,
                    from_name=campaign.from_name or None,
                    from_email=campaign.from_email or None,
                    reply_to=campaign.reply_to_email or None,
                )
                status = 'sent'
                error_msg = ''
                ses_id = result.get('message_id', '')
            except Exception as e:
                status = 'failed'
                error_msg = str(e)
                ses_id = ''

            EmailLog.objects.create(
                campaign=campaign,
                prospect=prospect,
                to_email=prospect.email,
                subject=rendered_subject,
                body_html=rendered_body,
                sequence_number=seq_num,
                ab_variant=variant,
                status=status,
                ses_message_id=ses_id,
                error_message=error_msg,
                triggered_by='management_command',
            )

            if status == 'sent':
                prospect.emails_sent += 1
                prospect.last_emailed_at = timezone.now()
                if prospect.status == 'new':
                    prospect.status = 'contacted'
                prospect.save(update_fields=['emails_sent', 'last_emailed_at', 'status', 'updated_at'])
                self.stdout.write(self.style.SUCCESS(line))
                sent += 1
            else:
                self.stdout.write(self.style.ERROR(f'{line} FAILED: {error_msg}'))

        self.stdout.write(f'\nDone. {"Previewed" if dry_run else "Sent"}: {sent}')
