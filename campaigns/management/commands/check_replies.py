"""
Check IMAP mailboxes for inbound replies, classify them, and execute auto-actions.

Supports multiple mailboxes via MailboxConfig model.
Falls back to settings.ZOHO_IMAP_* if no MailboxConfig records exist (backward compatible).

Run via cron every 5 minutes:
    */5 * * * * cd /path/to/paperclip-outreach && venv/bin/python manage.py check_replies

Safe to run repeatedly - deduplicates via Message-ID.
"""
import imaplib
import email
import logging
import re
from email.utils import parseaddr, parsedate_to_datetime

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from django.db.models import Q

from campaigns.models import (
    Campaign, Prospect, EmailLog, EmailQueue,
    InboundEmail, Suppression, ReplyTemplate, MailboxConfig,
)
from campaigns.email_service import EmailService

logger = logging.getLogger(__name__)


# Classification rules - checked in order, first match wins
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
        'want to learn more', 'set up a time', 'set up a meeting',
        'teams meeting', 'zoom meeting', 'book a call', 'grab a time',
        'would like to chat', 'give me a call', 'send me the brochure',
        'send me details', 'send me more info', 'yes please',
        'meeting next week', 'chat next week', 'call next week',
    ]),
]


def strip_quoted_text(body: str) -> str:
    """Remove quoted original email text, keeping only the new reply."""
    # Normalize non-breaking spaces to regular spaces
    body = body.replace('\xa0', ' ').replace('\u200b', '')
    # Split inline "Sent from my iPhone" so text before it is preserved
    body = re.sub(r'\s*Sent from my (iPhone|iPad|Samsung|Galaxy|Android)', r'\nSent from my \1', body, flags=re.IGNORECASE)
    # Handle iPhone-style inline quotes where "Sent from my iPhone" runs into "On ... wrote:"
    body = re.sub(r'(Sent from my (?:iPhone|iPad|Samsung|Galaxy|Android))\s*On ', r'\1\nOn ', body, flags=re.IGNORECASE)
    lines = body.split('\n')
    quote_patterns = [
        re.compile(r'^On .+ wrote:\s*$', re.IGNORECASE),
        re.compile(r'On .+wrote:', re.IGNORECASE),
        re.compile(r'^-{3,}\s*Original Message\s*-{3,}', re.IGNORECASE),
        re.compile(r'^(From|Da|Från|Von|De|Van)\s*:', re.IGNORECASE),
        re.compile(r'^Sent from my (iPhone|iPad|Samsung|Galaxy|Android)', re.IGNORECASE),
    ]

    cut_index = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        for pattern in quote_patterns:
            if pattern.search(stripped):
                cut_index = i
                break
        if cut_index != len(lines):
            break

    new_text = '\n'.join(lines[:cut_index])
    cleaned_lines = [l for l in new_text.split('\n') if not l.strip().startswith('>')]
    return '\n'.join(cleaned_lines).strip()


def classify_email(subject: str, body: str) -> str:
    """Classify an email by keyword matching. Returns classification string."""
    clean_body = strip_quoted_text(body)
    text = f'{subject}\n{clean_body}'.lower()

    for classification, keywords in CLASSIFICATION_RULES:
        for keyword in keywords:
            if keyword in text:
                return classification

    if '?' in clean_body:
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
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        html = payload.decode(charset, errors='replace')
                    except (LookupError, UnicodeDecodeError):
                        html = payload.decode('utf-8', errors='replace')
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
    help = 'Check IMAP mailboxes for reply emails, classify, and execute auto-actions'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
        parser.add_argument('--limit', type=int, default=0, help='Max emails to process per mailbox (0=no limit)')
        parser.add_argument('--campaign', help='Only process replies for this campaign name')
        parser.add_argument('--mailbox', help='Only check this mailbox (campaign name or product)')
        parser.add_argument('--product-slug', help='Only check mailboxes for campaigns with this product_ref slug (v2)')
        parser.add_argument('--exclude-product-slug', help='Exclude mailboxes for campaigns with this product_ref slug (v2)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        campaign_filter = options.get('campaign')
        mailbox_filter = options.get('mailbox')
        product_slug = options.get('product_slug')
        exclude_product_slug = options.get('exclude_product_slug')

        # Build list of mailboxes to check
        mailboxes = self._get_mailboxes(campaign_filter, mailbox_filter, product_slug, exclude_product_slug)

        if not mailboxes:
            self.stderr.write(self.style.ERROR(
                'No mailboxes configured. Either create MailboxConfig records in admin '
                'or set ZOHO_IMAP_EMAIL/ZOHO_IMAP_PASSWORD in .env'
            ))
            return

        total_processed = 0
        total_actions = {}

        for mb_info in mailboxes:
            label = mb_info.get('label', mb_info['imap_email'])
            self.stdout.write(f'\n{"=" * 60}')
            self.stdout.write(f'Mailbox: {label}')
            self.stdout.write(f'{"=" * 60}')

            processed, actions = self._process_mailbox(
                imap_host=mb_info['imap_host'],
                imap_port=mb_info['imap_port'],
                imap_email=mb_info['imap_email'],
                imap_password=mb_info['imap_password'],
                campaign=mb_info.get('campaign'),
                mailbox_obj=mb_info.get('mailbox_obj'),
                dry_run=dry_run,
                limit=limit,
            )

            total_processed += processed
            for cls, count in actions.items():
                total_actions[cls] = total_actions.get(cls, 0) + count

        # Grand summary
        self.stdout.write(f'\n{"=" * 60}')
        self.stdout.write(f'TOTAL: {total_processed} email(s) processed across {len(mailboxes)} mailbox(es)')
        for cls, count in total_actions.items():
            if count:
                self.stdout.write(f'  {cls}: {count}')
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] No changes were made.'))

    def _get_mailboxes(self, campaign_filter, mailbox_filter, product_slug=None, exclude_product_slug=None):
        """Build list of mailbox configs to check. Falls back to settings.py."""

        # Check for MailboxConfig records in DB
        mb_qs = MailboxConfig.objects.filter(is_active=True).select_related('campaign__product_ref')

        if mailbox_filter:
            mb_qs = mb_qs.filter(
                Q(campaign__name__icontains=mailbox_filter) |
                Q(campaign__product__icontains=mailbox_filter)
            )

        if campaign_filter:
            mb_qs = mb_qs.filter(campaign__name__icontains=campaign_filter)

        if product_slug:
            mb_qs = mb_qs.filter(campaign__product_ref__slug=product_slug)

        if exclude_product_slug:
            mb_qs = mb_qs.exclude(campaign__product_ref__slug=exclude_product_slug)

        if mb_qs.exists():
            # Deduplicate by IMAP email - multiple campaigns can share one inbox
            # Group campaigns by imap_email so we only connect once per inbox
            seen_emails = {}
            for mb in mb_qs:
                key = mb.imap_email.lower()
                if key not in seen_emails:
                    seen_emails[key] = {
                        'label': f'{mb.imap_email}',
                        'imap_host': mb.imap_host,
                        'imap_port': mb.imap_port,
                        'imap_email': mb.imap_email,
                        'imap_password': mb.imap_password,
                        'campaign': None,  # search across all campaigns for this inbox
                        'mailbox_obj': mb,
                        'campaigns': [mb.campaign],
                    }
                else:
                    seen_emails[key]['campaigns'].append(mb.campaign)

            # If only one campaign for this inbox, scope to it
            for key, info in seen_emails.items():
                if len(info['campaigns']) == 1:
                    info['campaign'] = info['campaigns'][0]
                    info['label'] = f'{info["campaigns"][0].name} <{info["imap_email"]}>'
                else:
                    names = ', '.join(c.name for c in info['campaigns'])
                    info['label'] = f'{info["imap_email"]} ({len(info["campaigns"])} campaigns)'

            return list(seen_emails.values())

        # Fallback: use settings.py (backward compatible with existing TaggIQ setup)
        if settings.ZOHO_IMAP_EMAIL and settings.ZOHO_IMAP_PASSWORD:
            campaign_obj = None
            if campaign_filter:
                campaign_obj = Campaign.objects.filter(name__icontains=campaign_filter).first()

            return [
                {
                    'label': f'Settings fallback <{settings.ZOHO_IMAP_EMAIL}>',
                    'imap_host': settings.ZOHO_IMAP_HOST,
                    'imap_port': settings.ZOHO_IMAP_PORT,
                    'imap_email': settings.ZOHO_IMAP_EMAIL,
                    'imap_password': settings.ZOHO_IMAP_PASSWORD,
                    'campaign': campaign_obj,
                    'mailbox_obj': None,
                }
            ]

        return []

    def _process_mailbox(self, imap_host, imap_port, imap_email, imap_password,
                         campaign, mailbox_obj, dry_run, limit):
        """Process a single IMAP mailbox. Returns (processed_count, actions_dict)."""

        actions = {'opt_out': 0, 'bounce': 0, 'not_interested': 0, 'out_of_office': 0,
                   'interested': 0, 'question': 0, 'other': 0}
        processed = 0
        skipped_dedup = 0
        skipped_no_match = 0

        # Connect to IMAP
        self.stdout.write(f'Connecting to {imap_host}:{imap_port}...')
        try:
            imap = imaplib.IMAP4_SSL(imap_host, imap_port)
            imap.login(imap_email, imap_password)
            imap.select('INBOX')
        except Exception as e:
            error_msg = f'IMAP connection failed: {e}'
            self.stderr.write(self.style.ERROR(error_msg))
            if mailbox_obj and not dry_run:
                mailbox_obj.last_error = error_msg
                mailbox_obj.save(update_fields=['last_error', 'updated_at'])
            return 0, actions

        self.stdout.write(self.style.SUCCESS(f'Connected to {imap_email}'))

        # Clear last error on successful connect
        # Update ALL MailboxConfigs sharing this email (one inbox, multiple campaigns)
        if not dry_run:
            now = timezone.now()
            updated = MailboxConfig.objects.filter(
                imap_email__iexact=imap_email, is_active=True
            ).update(last_error='', last_checked_at=now, updated_at=now)
            if updated:
                self.stdout.write(f'Updated last_checked_at on {updated} mailbox config(s).')

        # Search for unseen messages
        try:
            status, data = imap.search(None, 'UNSEEN')
            if status != 'OK':
                self.stderr.write(self.style.ERROR(f'IMAP search failed: {status}'))
                imap.logout()
                return 0, actions
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'IMAP search error: {e}'))
            imap.logout()
            return 0, actions

        msg_ids = data[0].split() if data[0] else []
        self.stdout.write(f'Found {len(msg_ids)} unseen message(s).')

        if not msg_ids:
            imap.logout()
            return 0, actions

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

                # Parse date
                date_str = msg.get('Date', '')
                try:
                    received_at = parsedate_to_datetime(date_str)
                    if received_at.tzinfo is not None:
                        received_at = received_at.replace(tzinfo=None)
                except Exception:
                    received_at = timezone.now()

                # Extract body
                body_text = extract_text_body(msg)

                # Match to prospect
                # If we have a specific campaign (from MailboxConfig), scope to it
                # Otherwise search across all campaigns (legacy fallback)
                if campaign:
                    prospect_qs = Prospect.objects.filter(
                        email__iexact=from_email_addr, campaign=campaign
                    )
                else:
                    prospect_qs = Prospect.objects.filter(email__iexact=from_email_addr)

                prospect = prospect_qs.select_related('campaign').first()

                # If mailbox is campaign-specific but no match, also try cross-campaign
                if not prospect and campaign:
                    prospect = Prospect.objects.filter(
                        email__iexact=from_email_addr
                    ).select_related('campaign').first()

                # Fuzzy match via In-Reply-To: prospect replied from a different domain
                # Match the SES message ID stored in EmailLog back to a prospect
                if not prospect and in_reply_to:
                    ses_id = in_reply_to.strip('<>').split('@')[0]
                    log = EmailLog.objects.filter(
                        ses_message_id__icontains=ses_id
                    ).select_related('prospect__campaign').first()
                    if log and log.prospect:
                        prospect = log.prospect
                        self.stdout.write(self.style.WARNING(
                            f'  FUZZY MATCH (In-Reply-To): {from_email_addr} -> {prospect.email} ({prospect.business_name})'
                        ))

                # Last resort: match by first name against decision_maker_name (only if unique match)
                if not prospect and from_name:
                    first_name = from_name.strip().split()[0]
                    qs = Prospect.objects.filter(
                        decision_maker_name__icontains=first_name,
                        emails_sent__gt=0,
                    ).select_related('campaign')
                    if campaign:
                        qs = qs.filter(campaign=campaign)
                    if qs.count() == 1:
                        prospect = qs.first()
                        self.stdout.write(self.style.WARNING(
                            f'  NAME MATCH: {from_email_addr} -> {prospect.email} ({prospect.business_name})'
                        ))

                if not prospect:
                    skipped_no_match += 1
                    # Mark as read so we don't reprocess
                    if not dry_run:
                        imap.store(msg_id, '+FLAGS', '\\Seen')

                    # For campaign-specific mailboxes: only save if it looks like
                    # a real reply (has In-Reply-To header). Skip notifications,
                    # newsletters, daft.ie alerts, etc.
                    if campaign and not in_reply_to:
                        continue

                    # For multi-campaign inboxes (campaign=None), try to find the
                    # campaign via In-Reply-To -> EmailLog -> campaign
                    no_match_campaign = campaign
                    if not no_match_campaign and in_reply_to:
                        ses_id = in_reply_to.strip('<>').split('@')[0]
                        log = EmailLog.objects.filter(
                            ses_message_id__icontains=ses_id
                        ).select_related('campaign').first()
                        if log and log.campaign:
                            no_match_campaign = log.campaign

                    # Only flag as needs_reply if we found a campaign
                    # (it's a real reply to our outreach). No campaign = newsletter/junk.
                    needs_reply_flag = bool(no_match_campaign)

                    self.stdout.write(self.style.WARNING(
                        f'  NO MATCH: {from_email_addr} - {subject[:60]}'
                    ))
                    if not dry_run:
                        InboundEmail.objects.create(
                            prospect=None,
                            campaign=no_match_campaign,
                            from_email=from_email_addr,
                            from_name=from_name,
                            subject=subject,
                            body_text=body_text[:10000],
                            message_id=message_id,
                            in_reply_to=in_reply_to,
                            classification='other',
                            needs_reply=needs_reply_flag,
                            received_at=received_at,
                            notes=f'No matching prospect found. Mailbox: {imap_email}',
                        )
                    continue

                matched_campaign = prospect.campaign

                # Find most recent EmailLog for sequence tracking
                last_log = EmailLog.objects.filter(
                    prospect=prospect, status='sent'
                ).order_by('-sequence_number').first()
                replied_to_sequence = last_log.sequence_number if last_log else None

                # Classify
                classification = classify_email(subject, body_text)
                actions[classification] += 1

                needs_reply = classification in ('interested', 'question', 'other')

                label = f'{prospect.business_name} <{from_email_addr}>'
                self.stdout.write(
                    f'  {classification.upper():15s} {label} - {subject[:50]}'
                )

                if dry_run:
                    processed += 1
                    continue

                # Save InboundEmail
                inbound = InboundEmail.objects.create(
                    prospect=prospect,
                    campaign=matched_campaign,
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

                # Execute auto-actions (opt-out, bounce, not-interested, etc.)
                self._execute_actions(prospect, inbound, classification)

                # Auto-reply if campaign has it enabled and template exists
                if (matched_campaign.auto_reply_enabled
                        and classification in ('interested', 'question')
                        and needs_reply):
                    self._try_auto_reply(prospect, inbound, matched_campaign, mailbox_obj)

                # Mark IMAP message as SEEN
                imap.store(msg_id, '+FLAGS', '\\Seen')
                processed += 1

            except Exception as e:
                logger.exception(f'Error processing IMAP message {msg_id}: {e}')
                self.stderr.write(self.style.ERROR(f'  ERROR processing message: {e}'))

        imap.logout()

        # Summary for this mailbox
        self.stdout.write(f'\nProcessed: {processed}, Dedup: {skipped_dedup}, No match: {skipped_no_match}')

        return processed, actions

    def _try_auto_reply(self, prospect, inbound, campaign, mailbox_obj):
        """Send a template-based auto-reply if template exists for this campaign+classification."""
        template = ReplyTemplate.objects.filter(
            campaign=campaign,
            classification=inbound.classification,
            is_active=True,
        ).first()

        if not template:
            self.stdout.write(f'    -> No active reply template for {campaign.name}/{inbound.classification}')
            return

        # Build template variables
        fname = prospect.decision_maker_name.split()[0] if prospect.decision_maker_name else 'there'
        variables = {
            'FNAME': fname,
            'COMPANY': prospect.business_name,
            'CITY': prospect.city,
            'SEGMENT': prospect.get_segment_display() if prospect.segment else prospect.business_type,
            'ORIGINAL_SUBJECT': inbound.subject,
            'ORIGINAL_BODY_SHORT': inbound.body_text[:500],
        }

        rendered_subject = EmailService.render_template(template.subject_template, variables)
        rendered_body = EmailService.render_template(template.body_html_template, variables)

        # Get SMTP config: prefer mailbox, fallback to settings
        smtp_config = mailbox_obj.get_smtp_config() if mailbox_obj else None

        try:
            result = EmailService.send_reply(
                to_email=inbound.from_email,
                subject=rendered_subject,
                body_html=rendered_body,
                in_reply_to=inbound.message_id,
                references=inbound.in_reply_to or inbound.message_id,
                from_email=campaign.from_email or None,
                from_name=campaign.from_name or None,
                smtp_config=smtp_config,
            )

            # Log the reply
            EmailLog.objects.create(
                campaign=campaign,
                prospect=prospect,
                to_email=inbound.from_email,
                subject=rendered_subject,
                body_html=rendered_body,
                sequence_number=0,
                template_name=f'auto_reply_{inbound.classification}',
                status='sent',
                ses_message_id=result.get('message_id', ''),
                triggered_by='auto_reply',
            )

            # Update inbound
            inbound.replied = True
            inbound.auto_replied = True
            inbound.reply_sent_at = timezone.now()
            inbound.needs_reply = False
            inbound.save(update_fields=[
                'replied', 'auto_replied', 'reply_sent_at', 'needs_reply', 'updated_at'
            ])

            self.stdout.write(self.style.SUCCESS(
                f'    -> Auto-replied ({inbound.classification}) to {inbound.from_email}'
            ))

        except Exception as e:
            logger.exception(f'Auto-reply failed for {inbound.from_email}: {e}')
            self.stderr.write(self.style.ERROR(f'    -> Auto-reply FAILED: {e}'))

    def _execute_actions(self, prospect, inbound, classification):
        """Execute automated actions based on classification. No email sending."""

        if classification == 'opt_out':
            prospect.status = 'opted_out'
            prospect.send_enabled = False
            prospect.save(update_fields=['status', 'send_enabled', 'updated_at'])
            # Product-scoped suppression: opt-out only blocks this product, not all products
            product_ref = prospect.campaign.product_ref if prospect.campaign else None
            Suppression.objects.get_or_create(
                email=prospect.email,
                product=product_ref,
                defaults={'reason': 'opt_out', 'notes': f'Auto-detected from reply: {inbound.subject[:100]}'}
            )
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
            # Bounces are product-scoped too (email may work for other products)
            product_ref = prospect.campaign.product_ref if prospect.campaign else None
            Suppression.objects.get_or_create(
                email=prospect.email,
                product=product_ref,
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
