"""
Interactive review of inbound replies that need a human response.

Usage:
    python manage.py review_replies
    python manage.py review_replies --campaign "BNI Embroidery"

Workflow:
1. Shows each flagged reply with prospect context
2. User drafts reply (with Claude Code assistance)
3. Send via Zoho SMTP with proper threading headers
4. Updates prospect status and InboundEmail record
"""
import sys
import textwrap

from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.models import InboundEmail, EmailLog
from campaigns.email_service import EmailService


class Command(BaseCommand):
    help = 'Interactive review and reply to inbound emails that need a response'

    def add_arguments(self, parser):
        parser.add_argument('--campaign', help='Only show replies for this campaign')

    def handle(self, *args, **options):
        campaign_filter = options.get('campaign')

        qs = InboundEmail.objects.filter(
            needs_reply=True, replied=False, auto_replied=False,
        ).select_related('prospect', 'campaign').order_by('received_at')

        if campaign_filter:
            qs = qs.filter(campaign__name__icontains=campaign_filter)

        replies = list(qs)

        if not replies:
            self.stdout.write(self.style.SUCCESS('No replies need attention. All caught up!'))
            return

        self.stdout.write(f'\n{len(replies)} reply(ies) need attention.\n')

        for i, inbound in enumerate(replies, 1):
            prospect = inbound.prospect
            campaign = inbound.campaign

            # Header
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write(f'  [{i}/{len(replies)}]')

            if prospect:
                self.stdout.write(f'  From: {inbound.from_name} <{inbound.from_email}>')
                self.stdout.write(f'  Company: {prospect.business_name} ({campaign.name if campaign else "?"})')
                self.stdout.write(f'  Status: {prospect.status} | Tier: {prospect.tier} | Score: {prospect.score}')
                if inbound.replied_to_sequence:
                    self.stdout.write(f'  Replied to: Sequence {inbound.replied_to_sequence}')
                if prospect.decision_maker_name:
                    self.stdout.write(f'  Contact: {prospect.decision_maker_name} ({prospect.decision_maker_title})')
                if prospect.current_tools:
                    self.stdout.write(f'  Tools: {prospect.current_tools}')
                if prospect.pain_signals:
                    self.stdout.write(f'  Pain: {prospect.pain_signals}')
            else:
                self.stdout.write(f'  From: {inbound.from_name} <{inbound.from_email}>')
                self.stdout.write(f'  (No matching prospect)')

            self.stdout.write(f'  Classification: {inbound.classification}')
            self.stdout.write(f'  Received: {inbound.received_at.strftime("%Y-%m-%d %H:%M")}')
            self.stdout.write(f'  Subject: {inbound.subject}')
            self.stdout.write('-' * 60)

            # Body (wrapped for readability)
            body_lines = inbound.body_text.strip()[:2000]
            wrapped = textwrap.fill(body_lines, width=76, initial_indent='  ', subsequent_indent='  ')
            self.stdout.write(wrapped)

            self.stdout.write('-' * 60)

            if inbound.notes:
                self.stdout.write(f'  Notes: {inbound.notes}')

            # Action prompt
            self.stdout.write('')
            self.stdout.write('  [S]end reply  [K]skip  [O]pt-out  [N]ot interested  [Q]uit')
            try:
                choice = input('  > ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write('\nExiting.')
                return

            if choice == 'q':
                self.stdout.write('Exiting.')
                return

            elif choice == 'k':
                self.stdout.write(self.style.WARNING('  Skipped.'))
                continue

            elif choice == 'o':
                # Mark as opt-out
                if prospect:
                    from campaigns.models import Suppression, EmailQueue
                    prospect.status = 'opted_out'
                    prospect.send_enabled = False
                    prospect.save(update_fields=['status', 'send_enabled', 'updated_at'])
                    Suppression.objects.get_or_create(
                        email=prospect.email,
                        defaults={'reason': 'opt_out', 'notes': f'Manual opt-out from review_replies'}
                    )
                    EmailQueue.objects.filter(
                        prospect=prospect, status='pending'
                    ).update(status='cancelled', error_message='Manual opt-out')
                inbound.needs_reply = False
                inbound.classification = 'opt_out'
                inbound.status_updated = True
                inbound.save(update_fields=['needs_reply', 'classification', 'status_updated', 'updated_at'])
                self.stdout.write(self.style.SUCCESS('  Opted out and suppressed.'))
                continue

            elif choice == 'n':
                # Mark as not interested
                if prospect:
                    from campaigns.models import EmailQueue
                    prospect.status = 'not_interested'
                    prospect.send_enabled = False
                    prospect.save(update_fields=['status', 'send_enabled', 'updated_at'])
                    EmailQueue.objects.filter(
                        prospect=prospect, status='pending'
                    ).update(status='cancelled', error_message='Manual not-interested')
                inbound.needs_reply = False
                inbound.classification = 'not_interested'
                inbound.status_updated = True
                inbound.save(update_fields=['needs_reply', 'classification', 'status_updated', 'updated_at'])
                self.stdout.write(self.style.SUCCESS('  Marked not interested, sending disabled.'))
                continue

            elif choice == 's':
                self._send_reply(inbound, prospect, campaign)

            else:
                self.stdout.write(self.style.WARNING('  Unknown option, skipping.'))
                continue

        self.stdout.write(self.style.SUCCESS('\nAll replies reviewed!'))

    def _send_reply(self, inbound, prospect, campaign):
        """Prompt for reply text, send via Zoho SMTP, log it."""
        self.stdout.write('\n  Paste your reply below. End with an empty line:')
        lines = []
        try:
            while True:
                line = input()
                if line == '':
                    if lines:
                        break
                    continue  # Skip leading empty lines
                lines.append(line)
        except (EOFError, KeyboardInterrupt):
            self.stdout.write('\n  Cancelled.')
            return

        reply_text = '\n'.join(lines)
        if not reply_text.strip():
            self.stdout.write(self.style.WARNING('  Empty reply, skipping.'))
            return

        # Confirm
        self.stdout.write(f'\n  Reply ({len(reply_text)} chars):')
        preview = textwrap.fill(reply_text[:300], width=76, initial_indent='  ', subsequent_indent='  ')
        self.stdout.write(preview)
        if len(reply_text) > 300:
            self.stdout.write('  ...')

        try:
            confirm = input('\n  Send? [Y]es / [N]o > ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.stdout.write('\n  Cancelled.')
            return

        if confirm not in ('y', 'yes'):
            self.stdout.write(self.style.WARNING('  Not sent.'))
            return

        # Build subject
        subject = inbound.subject
        if not subject.lower().startswith('re:'):
            subject = f'Re: {subject}'

        # Convert plain text to HTML
        body_html = reply_text.replace('\n', '<br>\n')

        # Determine from address
        from_email = campaign.from_email if campaign else None
        from_name = campaign.from_name if campaign else None

        try:
            result = EmailService.send_reply(
                to_email=inbound.from_email,
                subject=subject,
                body_html=body_html,
                in_reply_to=inbound.message_id,
                references=inbound.in_reply_to or inbound.message_id,
                from_email=from_email,
                from_name=from_name,
            )

            # Log to EmailLog
            if prospect and campaign:
                EmailLog.objects.create(
                    campaign=campaign,
                    prospect=prospect,
                    to_email=inbound.from_email,
                    subject=subject,
                    body_html=body_html,
                    sequence_number=0,  # 0 = manual reply, not a sequence email
                    template_name='manual_reply',
                    status='sent',
                    ses_message_id=result.get('message_id', ''),
                    triggered_by='manual_reply',
                )

            # Update inbound record
            inbound.replied = True
            inbound.reply_sent_at = timezone.now()
            inbound.needs_reply = False
            inbound.save(update_fields=['replied', 'reply_sent_at', 'needs_reply', 'updated_at'])

            # Escalate prospect status if appropriate
            if prospect:
                from campaigns.management.commands.check_replies import STATUS_RANK
                current_rank = STATUS_RANK.get(prospect.status, 0)
                if current_rank < STATUS_RANK.get('engaged', 2):
                    prospect.status = 'engaged'
                    prospect.save(update_fields=['status', 'updated_at'])

            self.stdout.write(self.style.SUCCESS(
                f'  Reply sent to {inbound.from_email} via Zoho SMTP!'
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  Failed to send reply: {e}'))
