"""
Check Zoho IMAP for inbound replies, classify them, and execute auto-actions.

Run via cron every 5 minutes:
    */5 * * * * cd /path/to/paperclip-outreach && venv/bin/python manage.py check_replies

Safe to run repeatedly — deduplicates via Message-ID.
"""
import imaplib
import email
import logging
import re
from email.utils import parseaddr, parsedate_to_datetime

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from campaigns.models import Campaign, Prospect, EmailLog, EmailQueue, InboundEmail, Suppression

logger = logging.getLogger(__name__)


# Classification rules — checked in order, first match wins
CLASSIFICATION_RULES = [
    ('opt_out', [
        'unsubscribe', 'remove me', 'stop emailing', 'take me off', 'opt out',
        'opt-out', 'do not contact', 'remove from list',
    ]),
    ('out_of_office', [
        'out of office', 'ooo', 'automatic reply', 'auto-reply', 'auto reply',
        'currently unavailable', 'will be back', 'away from', 'on vacation',
        'on holiday', 'limited access to email',
    ]),
    ('bounce', [
        'delivery status', 'undeliverable', 'mail delivery failed',
        'delivery failure', 'message not delivered', 'could not be delivered',
        'returned mail', 'delivery has failed',
    ]),
    ('not_interested', [
        'not interested', 'no thanks', 'no thank you', 'not for us',
        'not relevant', 'no need', 'not looking', 'pass on this',
    ]),
    ('interested', [
        'interested', 'tell me more', 'sounds good', 'sounds great',
        "let's talk", "let's chat", 'happy to chat', 'love to hear',
        'show me', 'demo', 'schedule', 'call me', 'sign me up',
        'want to learn more', 'set up a time',
    ]),
]


def classify_email(subject: str, body: str) -> str:
    """Classify an email by keyword matching. Returns classification string."""
    text = f'{subject}\n{body}'.lower()

    for classification, keywords in CLASSIFICATION_RULES:
        for keyword in keywords:
            if keyword in text:
                return classification

    # If contains a question mark and not matched above, it's a question
    if '?' in body:
        return 'question'

    return 'other'


def extract_text_body(msg: email.message.Message) -> str:
    """Extract the text/plain body from a MIME email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        return payload.decode(charset, errors='replace')
                    except (LookupError, UnicodeDecodeError):
                        return payload.decode('utf-8', errors='replace')
        # Fallback: try text/html if no text/plain
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        html = payload.decode(charset, errors='replace')
                    except (LookupError, UnicodeDecodeError):
                        html = payload.decode('utf-8', errors='replace')
                    # Strip HTML tags for classification
                    return re.sub(r'<[^>]+>', '', html)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            try:
                return payload.decode(charset, errors='replace')
            except (LookupError, UnicodeDecodeError):
                return payload.decode('utf-8', errors='replace')
    return ''


# Status escalation: only upgrade, never downgrade
STATUS_RANK = {
    'new': 0, 'contacted': 1, 'engaged': 2, 'interested': 3,
    'demo_scheduled': 4, 'design_partner': 5,
    'not_interested': -1, 'opted_out': -2,
}


class Command(BaseCommand):
    help = 'Check Zoho IMAP for reply emails, classify, and execute auto-actions'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
        parser.add_argument('--limit', type=int, default=0, help='Max emails to process (0=no limit)')
        parser.add_argument('--campaign', help='Only process replies for this campaign')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        campaign_filter = options.get('campaign')

        # Validate config
        if not settings.ZOHO_IMAP_EMAIL or not settings.ZOHO_IMAP_PASSWORD:
            self.stderr.write(self.style.ERROR(
                'ZOHO_IMAP_EMAIL and ZOHO_IMAP_PASSWORD must be set in .env'
            ))
            return

        # Connect to IMAP
        self.stdout.write(f'Connecting to {settings.ZOHO_IMAP_HOST}:{settings.ZOHO_IMAP_PORT}...')
        try:
            imap = imaplib.IMAP4_SSL(settings.ZOHO_IMAP_HOST, settings.ZOHO_IMAP_PORT)
            imap.login(settings.ZOHO_IMAP_EMAIL, settings.ZOHO_IMAP_PASSWORD)
            imap.select('INBOX')
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'IMAP connection failed: {e}'))
            return

        self.stdout.write(self.style.SUCCESS('Connected to Zoho IMAP.'))

        # Search for unseen messages
        try:
            status, data = imap.search(None, 'UNSEEN')
            if status != 'OK':
                self.stderr.write(self.style.ERROR(f'IMAP search failed: {status}'))
                imap.logout()
                return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'IMAP search error: {e}'))
            imap.logout()
            return

        msg_ids = data[0].split() if data[0] else []
        self.stdout.write(f'Found {len(msg_ids)} unseen message(s).')

        if not msg_ids:
            imap.logout()
            return

        # Pre-load campaign filter if specified
        campaign_obj = None
        if campaign_filter:
            campaign_obj = Campaign.objects.filter(name__icontains=campaign_filter).first()
            if not campaign_obj:
                self.stderr.write(self.style.ERROR(f'Campaign not found: {campaign_filter}'))
                imap.logout()
                return

        processed = 0
        skipped_dedup = 0
        skipped_no_match = 0
        actions = {'opt_out': 0, 'bounce': 0, 'not_interested': 0, 'out_of_office': 0,
                   'interested': 0, 'question': 0, 'other': 0}

        for msg_id in msg_ids:
            if limit and processed >= limit:
                self.stdout.write(f'Limit reached ({limit}).')
                break

            try:
                status, msg_data = imap.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Parse headers
                message_id = msg.get('Message-ID', '').strip()
                if not message_id:
                    message_id = f'no-msgid-{msg_id.decode()}-{timezone.now().isoformat()}'

                # Dedup check
                if InboundEmail.objects.filter(message_id=message_id).exists():
                    skipped_dedup += 1
                    continue

                from_name, from_email_addr = parseaddr(msg.get('From', ''))
                from_email_addr = from_email_addr.lower()
                subject = msg.get('Subject', '(no subject)')
                in_reply_to = msg.get('In-Reply-To', '').strip()

                # Parse date (naive datetime — USE_TZ=False with SQLite)
                date_str = msg.get('Date', '')
                try:
                    received_at = parsedate_to_datetime(date_str)
                    if received_at.tzinfo is not None:
                        received_at = received_at.replace(tzinfo=None)
                except Exception:
                    received_at = timezone.now()

                # Extract body
                body_text = extract_text_body(msg)

                # Match to prospect (case-insensitive email lookup)
                prospect_qs = Prospect.objects.filter(email__iexact=from_email_addr)
                if campaign_obj:
                    prospect_qs = prospect_qs.filter(campaign=campaign_obj)
                prospect = prospect_qs.select_related('campaign').first()

                if not prospect:
                    skipped_no_match += 1
                    # Still save for audit, but mark SEEN so we don't re-process
                    if not dry_run:
                        imap.store(msg_id, '+FLAGS', '\\Seen')
                    self.stdout.write(self.style.WARNING(
                        f'  NO MATCH: {from_email_addr} — {subject[:60]}'
                    ))
                    # Save unmatched inbound for manual review
                    if not dry_run:
                        InboundEmail.objects.create(
                            prospect=None,
                            campaign=None,
                            from_email=from_email_addr,
                            from_name=from_name,
                            subject=subject,
                            body_text=body_text[:10000],
                            message_id=message_id,
                            in_reply_to=in_reply_to,
                            classification='other',
                            needs_reply=True,
                            received_at=received_at,
                            notes='No matching prospect found.',
                        )
                    continue

                campaign = prospect.campaign

                # Find most recent EmailLog for this prospect to get sequence
                last_log = EmailLog.objects.filter(
                    prospect=prospect, status='sent'
                ).order_by('-sequence_number').first()
                replied_to_sequence = last_log.sequence_number if last_log else None

                # Classify
                classification = classify_email(subject, body_text)
                actions[classification] += 1

                # Determine needs_reply
                needs_reply = classification in ('interested', 'question', 'other')

                label = f'{prospect.business_name} <{from_email_addr}>'
                self.stdout.write(
                    f'  {classification.upper():15s} {label} — {subject[:50]}'
                )

                if dry_run:
                    processed += 1
                    continue

                # Save InboundEmail
                inbound = InboundEmail.objects.create(
                    prospect=prospect,
                    campaign=campaign,
                    from_email=from_email_addr,
                    from_name=from_name,
                    subject=subject,
                    body_text=body_text[:10000],
                    message_id=message_id,
                    in_reply_to=in_reply_to,
                    classification=classification,
                    replied_to_sequence=replied_to_sequence,
                    needs_reply=needs_reply,
                    received_at=received_at,
                )

                # Execute auto-actions
                self._execute_actions(prospect, inbound, classification)

                # Mark IMAP message as SEEN
                imap.store(msg_id, '+FLAGS', '\\Seen')
                processed += 1

            except Exception as e:
                logger.exception(f'Error processing IMAP message {msg_id}: {e}')
                self.stderr.write(self.style.ERROR(f'  ERROR processing message: {e}'))

        imap.logout()

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'Processed: {processed}')
        self.stdout.write(f'Skipped (dedup): {skipped_dedup}')
        self.stdout.write(f'Skipped (no match): {skipped_no_match}')
        for cls, count in actions.items():
            if count:
                self.stdout.write(f'  {cls}: {count}')
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] No changes were made.'))

    def _execute_actions(self, prospect, inbound, classification):
        """Execute automated actions based on classification. No email sending."""

        if classification == 'opt_out':
            prospect.status = 'opted_out'
            prospect.send_enabled = False
            prospect.save(update_fields=['status', 'send_enabled', 'updated_at'])
            Suppression.objects.get_or_create(
                email=prospect.email,
                defaults={'reason': 'opt_out', 'notes': f'Auto-detected from reply: {inbound.subject[:100]}'}
            )
            # Cancel pending queue items
            cancelled = EmailQueue.objects.filter(
                prospect=prospect, status='pending'
            ).update(status='cancelled', error_message='Prospect opted out')
            inbound.status_updated = True
            inbound.save(update_fields=['status_updated', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(
                f'    -> Opted out, suppressed, {cancelled} queued email(s) cancelled'
            ))

        elif classification == 'bounce':
            prospect.send_enabled = False
            prospect.save(update_fields=['send_enabled', 'updated_at'])
            Suppression.objects.get_or_create(
                email=prospect.email,
                defaults={'reason': 'bounce', 'notes': f'Bounce detected from reply: {inbound.subject[:100]}'}
            )
            inbound.status_updated = True
            inbound.save(update_fields=['status_updated', 'updated_at'])
            self.stdout.write(self.style.SUCCESS('    -> Suppressed (bounce), sending disabled'))

        elif classification == 'not_interested':
            prospect.status = 'not_interested'
            prospect.send_enabled = False
            prospect.save(update_fields=['status', 'send_enabled', 'updated_at'])
            cancelled = EmailQueue.objects.filter(
                prospect=prospect, status='pending'
            ).update(status='cancelled', error_message='Prospect not interested')
            inbound.status_updated = True
            inbound.save(update_fields=['status_updated', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(
                f'    -> Not interested, sending disabled, {cancelled} queued email(s) cancelled'
            ))

        elif classification == 'out_of_office':
            # Just note it, no status change
            note = f'[Auto] OOO reply received {timezone.now().strftime("%Y-%m-%d")}'
            if prospect.notes:
                prospect.notes = f'{note}\n{prospect.notes}'
            else:
                prospect.notes = note
            prospect.save(update_fields=['notes', 'updated_at'])
            inbound.status_updated = True
            inbound.save(update_fields=['status_updated', 'updated_at'])
            self.stdout.write('    -> Out of office noted')

        elif classification == 'interested':
            # Only escalate status, never downgrade
            current_rank = STATUS_RANK.get(prospect.status, 0)
            if current_rank < STATUS_RANK.get('interested', 3):
                prospect.status = 'interested'
                prospect.save(update_fields=['status', 'updated_at'])
                inbound.status_updated = True
                inbound.save(update_fields=['status_updated', 'updated_at'])
            self.stdout.write(self.style.SUCCESS('    -> Flagged as interested, needs reply'))

        elif classification == 'question':
            current_rank = STATUS_RANK.get(prospect.status, 0)
            if current_rank < STATUS_RANK.get('engaged', 2):
                prospect.status = 'engaged'
                prospect.save(update_fields=['status', 'updated_at'])
                inbound.status_updated = True
                inbound.save(update_fields=['status_updated', 'updated_at'])
            self.stdout.write(self.style.SUCCESS('    -> Question detected, needs reply'))

        elif classification == 'other':
            self.stdout.write('    -> Flagged for manual review')
