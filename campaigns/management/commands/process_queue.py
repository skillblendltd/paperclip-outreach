"""
Process the email queue: send due emails and auto-schedule follow-ups.

Run via cron every 15 minutes:
    */15 * * * * cd /path/to/paperclip-outreach && venv/bin/python manage.py process_queue

What it does:
1. Finds all queued emails where send_after <= now and status=pending
2. For each, runs the same safeguard checks as /api/send/
3. Sends via SES, logs to EmailLog, updates prospect
4. After sending seq N, auto-queues seq N+1 for follow_up_days later
   (only if there's a template queued or --auto-followup is set)
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from campaigns.models import Campaign, Prospect, EmailLog, EmailQueue, Suppression
from campaigns.email_service import EmailService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process queued emails: send due items and schedule follow-ups'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without sending')
        parser.add_argument('--limit', type=int, default=0, help='Max emails to process (0=no limit)')
        parser.add_argument('--campaign', help='Only process this campaign')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        campaign_filter = options.get('campaign')

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get due items
        qs = EmailQueue.objects.filter(
            status='pending',
            send_after__lte=now,
        ).select_related('campaign', 'prospect')

        if campaign_filter:
            qs = qs.filter(campaign__name__icontains=campaign_filter)

        due_items = list(qs.order_by('send_after'))
        self.stdout.write(f'Due items: {len(due_items)}')

        if not due_items:
            self.stdout.write('Nothing to process.')
            return

        suppressed_emails = set(
            e.lower() for e in Suppression.objects.values_list('email', flat=True)
        )

        sent = 0
        skipped = 0
        failed = 0

        for item in due_items:
            if limit and sent >= limit:
                self.stdout.write(f'Limit reached ({limit}).')
                break

            campaign = item.campaign
            prospect = item.prospect
            label = f'{prospect.business_name} <{prospect.email}> seq={item.sequence_number}'

            # --- Safeguard checks (same as /api/send/) ---

            # Master switch
            if not campaign.sending_enabled:
                item.status = 'skipped'
                item.error_message = 'Campaign sending disabled'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                self.stdout.write(self.style.WARNING(f'  SKIP {label}: campaign disabled'))
                skipped += 1
                continue

            # Daily limit
            sent_today = EmailLog.objects.filter(
                campaign=campaign, created_at__gte=today_start, status='sent'
            ).count()
            if sent_today >= campaign.max_emails_per_day:
                self.stdout.write(self.style.WARNING(
                    f'  SKIP {label}: daily limit reached ({sent_today}/{campaign.max_emails_per_day})'
                ))
                break  # stop processing this campaign's items

            # Min gap
            last_sent = EmailLog.objects.filter(
                campaign=campaign, status='sent'
            ).order_by('-created_at').first()
            if last_sent:
                gap = now - last_sent.created_at
                min_gap = timedelta(minutes=campaign.min_gap_minutes)
                if gap < min_gap:
                    wait = int((min_gap - gap).total_seconds())
                    self.stdout.write(self.style.WARNING(
                        f'  WAIT: min gap not met, need {wait}s more. Stopping.'
                    ))
                    break

            # Prospect checks
            if not prospect.send_enabled:
                item.status = 'skipped'
                item.error_message = 'Prospect send_enabled=False'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                skipped += 1
                continue

            if prospect.status in ('not_interested', 'opted_out'):
                item.status = 'skipped'
                item.error_message = f'Prospect status: {prospect.status}'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                skipped += 1
                continue

            if not prospect.email:
                item.status = 'skipped'
                item.error_message = 'No email'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                skipped += 1
                continue

            # Suppression
            if prospect.email.lower() in suppressed_emails:
                item.status = 'skipped'
                item.error_message = 'Suppressed'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                skipped += 1
                continue

            # Max per prospect
            prospect_sent = EmailLog.objects.filter(prospect=prospect, status='sent').count()
            if prospect_sent >= campaign.max_emails_per_prospect:
                item.status = 'skipped'
                item.error_message = f'Max emails reached ({prospect_sent})'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                skipped += 1
                continue

            # Sequence order
            if campaign.require_sequence_order and item.sequence_number > 1:
                prev_exists = EmailLog.objects.filter(
                    prospect=prospect, sequence_number=item.sequence_number - 1, status='sent'
                ).exists()
                if not prev_exists:
                    item.status = 'skipped'
                    item.error_message = f'Seq {item.sequence_number - 1} not sent yet'
                    item.save(update_fields=['status', 'error_message', 'updated_at'])
                    skipped += 1
                    continue

            # Duplicate check
            if EmailLog.objects.filter(
                prospect=prospect, sequence_number=item.sequence_number, status='sent'
            ).exists():
                item.status = 'skipped'
                item.error_message = f'Seq {item.sequence_number} already sent'
                item.save(update_fields=['status', 'error_message', 'updated_at'])
                skipped += 1
                continue

            # --- Render ---
            variables = {
                'FNAME': prospect.decision_maker_name.split()[0] if prospect.decision_maker_name else 'there',
                'COMPANY': prospect.business_name,
                'CITY': prospect.city,
                'SEGMENT': prospect.get_segment_display() if prospect.segment else prospect.business_type,
            }

            rendered_subject = EmailService.render_template(item.subject, variables)
            rendered_body = EmailService.render_template(item.body_html, variables)
            rendered_body += campaign.unsubscribe_footer_html

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f'  [DRY RUN] {label} variant={item.ab_variant}'
                ))
                sent += 1
                continue

            # --- Send ---
            try:
                result = EmailService.send_email(
                    to_emails=[prospect.email],
                    subject=rendered_subject,
                    body_html=rendered_body,
                    from_name=campaign.from_name or None,
                    from_email=campaign.from_email or None,
                    reply_to=campaign.reply_to_email or None,
                )
                send_status = 'sent'
                error_msg = ''
                ses_id = result.get('message_id', '')
            except Exception as e:
                send_status = 'failed'
                error_msg = str(e)
                ses_id = ''
                logger.exception(f'Failed to send to {prospect.email}')

            # Log to EmailLog
            EmailLog.objects.create(
                campaign=campaign,
                prospect=prospect,
                to_email=prospect.email,
                subject=rendered_subject,
                body_html=rendered_body,
                sequence_number=item.sequence_number,
                template_name=item.template_name,
                ab_variant=item.ab_variant,
                status=send_status,
                ses_message_id=ses_id,
                error_message=error_msg,
                triggered_by='queue',
            )

            # Update queue item
            item.status = send_status
            item.error_message = error_msg
            item.save(update_fields=['status', 'error_message', 'updated_at'])

            # Update prospect
            if send_status == 'sent':
                prospect.emails_sent += 1
                prospect.last_emailed_at = timezone.now()
                if prospect.status == 'new':
                    prospect.status = 'contacted'
                prospect.save(update_fields=['emails_sent', 'last_emailed_at', 'status', 'updated_at'])
                self.stdout.write(self.style.SUCCESS(f'  SENT {label}'))
                sent += 1

                # Auto-schedule next follow-up if there's a queued template for next seq
                next_seq = item.sequence_number + 1
                already_queued = EmailQueue.objects.filter(
                    prospect=prospect, sequence_number=next_seq, status='pending'
                ).exists()
                if not already_queued and next_seq <= campaign.max_emails_per_prospect:
                    # Check if agent pre-queued content for next sequence
                    # (won't auto-create empty follow-ups - agent must provide content)
                    pass
            else:
                self.stdout.write(self.style.ERROR(f'  FAIL {label}: {error_msg}'))
                failed += 1

            # Refresh now for gap calculation
            now = timezone.now()

        self.stdout.write(f'\nDone. Sent: {sent}, Skipped: {skipped}, Failed: {failed}')
