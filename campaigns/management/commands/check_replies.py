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

from django.db.models import F, Q

from campaigns.models import (
    Campaign, Prospect, EmailLog, EmailQueue,
    InboundEmail, Suppression, ReplyTemplate, MailboxConfig,
)
from campaigns.email_service import EmailService

logger = logging.getLogger(__name__)


# G4 (2026-04-15): system-email denylist.
# Inbounds matching these are forced to classification='other', needs_reply=False,
# needs_manual_review=False BEFORE the regular classifier runs. Prevents the AI
# reply pipeline from ever seeing DocuSign notifications, calendar invites,
# out-of-office auto-acks, postmaster bounces, or our own system emails.
SYSTEM_SENDER_DENYLIST_SUBSTRINGS = (
    'postmaster@',
    'mailer-daemon@',
    'noreply@',
    'no-reply@',
    'do-not-reply@',
    'bounces@',
    'dse@',                      # DocuSign notification sender
    'dse_na@',
    'dse_demo@',
    '@docusign.net',
    'calendar-notification@',
    'calendar-server@',
    'meetings@',
    'unknowngeneva@',
    'notifications@github.com',
    'notify@',
)
SYSTEM_SUBJECT_DENYLIST_PREFIXES = (
    'auto-reply:',
    'auto reply:',
    'automatic reply:',
    'out of office:',
    '[request received]',
    'accepted:',
    'declined:',
    'tentative:',
    'document for esignature',
    'please docusign:',
    'appointment booked:',
    'undeliverable:',
    'delivery status notification',
)


def is_system_email(from_email: str, subject: str) -> bool:
    """G4: return True iff this inbound should be archived silently.

    Catches system-generated email that has no human on the other end:
    DocuSign notifications, calendar invites, auto-acks, bounces,
    postmaster replies, GitHub notifications, etc.

    This runs BEFORE classification so the classifier never has a chance
    to tag a DocuSign notice as 'interested' based on an accidental
    keyword match.
    """
    lower_from = (from_email or '').lower()
    for needle in SYSTEM_SENDER_DENYLIST_SUBSTRINGS:
        if needle in lower_from:
            return True
    lower_subj = (subject or '').lower().strip()
    for prefix in SYSTEM_SUBJECT_DENYLIST_PREFIXES:
        if lower_subj.startswith(prefix):
            return True
    return False


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


def match_inbound_to_prospect(
    from_email: str,
    from_name: str,
    in_reply_to: str,
    mailbox_campaign=None,
    mailbox_campaigns=None,
    product_floor=None,
    stdout=None,
    style=None,
):
    """F1 — tenant-isolated inbound-to-prospect matching (2026-04-15).

    Returns ``(prospect_or_None, match_source, ambiguous)``.

    Precedence (first rule that returns wins; no fall-through to a less
    authoritative rule once a rule matches):

      1. **Thread ancestor** — parse ``In-Reply-To``, look up the outbound
         ``EmailLog`` whose ``ses_message_id`` contains the normalized ID,
         return ``email_log.prospect``. This is the ONLY unambiguous signal:
         it traces the reply back to the exact outbound message we sent,
         which has a definitive ``campaign`` FK.

      2. **Mailbox-scoped email match** — if we know the product floor of
         this mailbox (all campaigns on this inbox share one Product),
         restrict the ``Prospect.email`` lookup to campaigns within that
         Product. If still 0 matches, fall back to the mailbox's campaign
         set. Never reach outside the mailbox's tenant boundary.

      3. **Global fallback** — only runs when no product floor is known
         AND no thread ancestor exists. If the global email lookup returns
         exactly 1 prospect, use it. If it returns >1, return
         ``ambiguous=True`` so the caller can save the inbound with
         ``needs_manual_review=True`` and ``needs_reply=False``.

      4. **Name-based last resort** — same as before, but only when a
         single unique decision_maker_name match exists within the mailbox
         boundary. Does NOT run if step 3 returned ambiguous (we do not
         compound one uncertain signal with another).

    ``ambiguous`` is True only when:
      - Step 1 found no ancestor
      - Step 2 returned 0 rows OR was skipped (no product_floor)
      - Step 3 returned >1 rows across products

    Callers should check ``ambiguous`` FIRST: if True, save the inbound
    as needs_manual_review and skip auto-actions. A prospect is never
    returned alongside ambiguous=True.

    Args:
        from_email: normalized lowercase sender email
        from_name: raw ``From`` header name (may be empty)
        in_reply_to: raw ``In-Reply-To`` header value (may be empty)
        mailbox_campaign: single Campaign if inbox serves exactly one,
            else None
        mailbox_campaigns: list of Campaigns that share this inbox
        product_floor: the Product every campaign on this inbox belongs
            to, or None if the inbox spans multiple products (rare /
            misconfiguration)
        stdout, style: optional Django command output handles for
            verbose logging of match sources
    """
    mailbox_campaigns = mailbox_campaigns or []

    def _log(msg, styler=None):
        if stdout is None:
            return
        if styler is not None:
            stdout.write(styler(msg))
        else:
            stdout.write(msg)

    # ---------- Rule 1: thread ancestor via In-Reply-To ----------
    if in_reply_to:
        ses_id = in_reply_to.strip('<>').split('@')[0]
        if ses_id:
            log = EmailLog.objects.filter(
                ses_message_id__icontains=ses_id,
            ).select_related('prospect__campaign__product_ref').first()
            if log and log.prospect:
                _log(
                    f'  THREAD MATCH (In-Reply-To): {from_email} -> '
                    f'{log.prospect.email} ({log.prospect.business_name}) '
                    f'via EmailLog {log.id} campaign={log.campaign.name if log.campaign else "-"}',
                    style.SUCCESS if style else None,
                )
                return log.prospect, 'thread_ancestor', False

    # ---------- Rule 2: mailbox-scoped email match ----------
    #
    # Scope priority: product_floor > mailbox_campaigns > single campaign.
    # We only fall outside these boundaries if nothing in the mailbox
    # matches AND no product_floor exists.
    scoped_qs = None
    scope_label = None

    if product_floor is not None:
        scoped_qs = Prospect.objects.filter(
            email__iexact=from_email,
            campaign__product_ref=product_floor,
        )
        scope_label = f'product={product_floor.slug}'
    elif mailbox_campaigns:
        scoped_qs = Prospect.objects.filter(
            email__iexact=from_email,
            campaign__in=mailbox_campaigns,
        )
        scope_label = f'{len(mailbox_campaigns)} mailbox campaign(s)'
    elif mailbox_campaign is not None:
        scoped_qs = Prospect.objects.filter(
            email__iexact=from_email,
            campaign=mailbox_campaign,
        )
        scope_label = f'campaign={mailbox_campaign.name}'

    if scoped_qs is not None:
        scoped_count = scoped_qs.count()
        if scoped_count == 1:
            prospect = scoped_qs.select_related('campaign__product_ref').first()
            _log(
                f'  EMAIL MATCH (scoped {scope_label}): {from_email} -> '
                f'{prospect.email} ({prospect.business_name})',
            )
            return prospect, 'email_scoped', False
        if scoped_count > 1:
            # Multiple prospect rows for this email within the mailbox
            # boundary. No thread ancestor to disambiguate. Flag as
            # ambiguous — caller must not auto-reply.
            names = ', '.join(
                f'{p.business_name}({p.campaign.name})'
                for p in scoped_qs.select_related('campaign')[:3]
            )
            _log(
                f'  AMBIGUOUS (scoped {scope_label}, {scoped_count} matches): '
                f'{from_email} -> [{names}]',
                style.WARNING if style else None,
            )
            return None, 'ambiguous_scoped', True
        # scoped_count == 0: continue below. May fall through to global
        # fallback only if no product_floor was enforced.

    # ---------- Rule 3: global fallback (only if no product floor) ----------
    #
    # Product floor is the hardest tenant boundary we have. If it's set and
    # the scoped lookup returned 0, we do NOT reach outside it — that would
    # be a cross-product bleed (the exact bug F1 fixes). The inbound is
    # saved as no-match with no prospect.
    if product_floor is None:
        global_qs = Prospect.objects.filter(email__iexact=from_email)
        global_count = global_qs.count()
        if global_count == 1:
            prospect = global_qs.select_related('campaign__product_ref').first()
            _log(
                f'  EMAIL MATCH (global fallback): {from_email} -> '
                f'{prospect.email} ({prospect.business_name}) '
                f'campaign={prospect.campaign.name if prospect.campaign else "-"}',
            )
            return prospect, 'email_global', False
        if global_count > 1:
            # Cross-product collision with no thread ancestor. Ambiguous.
            products_hit = {
                p.campaign.product_ref.slug if p.campaign and p.campaign.product_ref else '?'
                for p in global_qs.select_related('campaign__product_ref')[:10]
            }
            _log(
                f'  AMBIGUOUS (global, {global_count} matches across products '
                f'{sorted(products_hit)}): {from_email}',
                style.WARNING if style else None,
            )
            return None, 'ambiguous_global', True

    # ---------- Rule 4: name-based last resort (never ambiguous) ----------
    if from_name:
        first_name = from_name.strip().split()[0] if from_name.strip() else ''
        if first_name:
            name_qs = Prospect.objects.filter(
                decision_maker_name__icontains=first_name,
                emails_sent__gt=0,
            ).select_related('campaign__product_ref')
            if product_floor is not None:
                name_qs = name_qs.filter(campaign__product_ref=product_floor)
            elif mailbox_campaigns:
                name_qs = name_qs.filter(campaign__in=mailbox_campaigns)
            elif mailbox_campaign is not None:
                name_qs = name_qs.filter(campaign=mailbox_campaign)
            if name_qs.count() == 1:
                prospect = name_qs.first()
                _log(
                    f'  NAME MATCH: {from_email} -> '
                    f'{prospect.email} ({prospect.business_name})',
                    style.WARNING if style else None,
                )
                return prospect, 'name', False

    return None, 'no_match', False


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
                product_floor=mb_info.get('product_floor'),
                mailbox_campaigns=mb_info.get('campaigns') or [],
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
            # Group campaigns by imap_email so we only connect once per inbox.
            #
            # F3 (2026-04-15 tenant isolation fix): each mailbox grouping carries
            # BOTH the list of campaigns it serves AND the Product floor those
            # campaigns share. `product_floor` is the Product that every campaign
            # on this inbox belongs to (None only if campaigns span >1 product,
            # which is a misconfiguration). Matching uses the floor to scope
            # email-based prospect lookups so inbound replies never attribute
            # to a prospect row outside this mailbox's Product boundary.
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
                        'campaign': None,  # set below if single-campaign inbox
                        'mailbox_obj': mb,
                        'campaigns': [mb.campaign],
                    }
                else:
                    seen_emails[key]['campaigns'].append(mb.campaign)

            for key, info in seen_emails.items():
                # Derive the Product floor for this mailbox. If every campaign on
                # this inbox shares the same Product, that Product is the floor
                # and email-based prospect matching is scoped to it.
                products = {
                    c.product_ref_id for c in info['campaigns'] if c.product_ref_id
                }
                if len(products) == 1:
                    info['product_floor'] = info['campaigns'][0].product_ref
                else:
                    # Mailbox spans >1 product or has no product_ref at all.
                    # Matching falls back to mailbox campaign set only.
                    info['product_floor'] = None

                if len(info['campaigns']) == 1:
                    info['campaign'] = info['campaigns'][0]
                    info['label'] = f'{info["campaigns"][0].name} <{info["imap_email"]}>'
                else:
                    floor_label = (
                        info['product_floor'].slug if info['product_floor'] else 'MIXED'
                    )
                    info['label'] = (
                        f'{info["imap_email"]} '
                        f'({len(info["campaigns"])} campaigns, product={floor_label})'
                    )

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
                         campaign, mailbox_obj, dry_run, limit,
                         product_floor=None, mailbox_campaigns=None):
        """Process a single IMAP mailbox. Returns (processed_count, actions_dict).

        product_floor / mailbox_campaigns (F3 — tenant isolation, 2026-04-15):
            Carried forward from `_get_mailboxes` grouping. They define the
            tenant boundary for email-based prospect matching — no unscoped
            cross-product lookups. See `_match_to_prospect` for the precedence
            rules.
        """
        mailbox_campaigns = mailbox_campaigns or []

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

                # F1 — tenant-isolated prospect matching (2026-04-15).
                # Replaces the old email-first lookup with a thread-first,
                # mailbox-scoped precedence. Details in `match_inbound_to_prospect`.
                prospect, match_source, ambiguous = match_inbound_to_prospect(
                    from_email=from_email_addr,
                    from_name=from_name,
                    in_reply_to=in_reply_to,
                    mailbox_campaign=campaign,
                    mailbox_campaigns=mailbox_campaigns,
                    product_floor=product_floor,
                    stdout=self.stdout,
                    style=self.style,
                )

                if not prospect:
                    skipped_no_match += 1
                    # Mark as read so we don't reprocess
                    if not dry_run:
                        imap.store(msg_id, '+FLAGS', '\\Seen')

                    # G4 (2026-04-15): system email with no prospect match —
                    # archive silently. Do not create an InboundEmail row at
                    # all, do not flag for review. Preserves the mailbox from
                    # filling with DocuSign/calendar/bounce noise rows.
                    if is_system_email(from_email_addr, subject):
                        self.stdout.write(self.style.WARNING(
                            f'  SYSTEM-ARCHIVED (no match): {from_email_addr} - {subject[:60]}'
                        ))
                        continue

                    # F1 (2026-04-15): if matching returned ambiguous (>1
                    # prospect rows for this email within the tenant boundary),
                    # save the inbound with needs_manual_review=True and
                    # needs_reply=False. Auto-reply pipeline must not touch it.
                    if ambiguous:
                        self.stdout.write(self.style.WARNING(
                            f'  NEEDS MANUAL REVIEW ({match_source}): '
                            f'{from_email_addr} - {subject[:60]}'
                        ))
                        if not dry_run:
                            InboundEmail.objects.create(
                                prospect=None,
                                campaign=campaign,  # may be None
                                from_email=from_email_addr,
                                from_name=from_name,
                                subject=subject,
                                body_text=body_text[:10000],
                                message_id=message_id,
                                in_reply_to=in_reply_to,
                                classification='other',
                                needs_reply=False,
                                needs_manual_review=True,
                                received_at=received_at,
                                notes=(
                                    f'Ambiguous match ({match_source}) from mailbox '
                                    f'{imap_email}. Multiple prospect rows matched by '
                                    f'email with no thread ancestor to disambiguate.'
                                ),
                            )
                        continue

                    # For campaign-specific mailboxes: only save if it looks like
                    # a real reply (has In-Reply-To header). Skip notifications,
                    # newsletters, daft.ie alerts, etc.
                    if campaign and not in_reply_to:
                        self.stdout.write(f'  SKIP (no In-Reply-To): {from_email_addr} - {subject[:60]}')
                        skipped_no_match += 1
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

                # G4 (2026-04-15): system-email denylist. DocuSign, calendar
                # invites, postmaster, auto-acks get archived silently before
                # they ever reach the classifier or the AI reply pipeline.
                is_system = is_system_email(from_email_addr, subject)

                # Classify
                if is_system:
                    classification = 'other'
                    needs_reply = False
                    actions['other'] += 1
                    self.stdout.write(self.style.WARNING(
                        f'  SYSTEM-ARCHIVED  {from_email_addr} - {subject[:50]}'
                    ))
                else:
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

                # H2 (2026-04-15): atomic reply counter update. Runs BEFORE
                # _execute_actions so the subsequent in-method `save(update_
                # fields=...)` calls do not clobber our F() write. Counts
                # real human replies only — system emails (DocuSign etc),
                # bounces, and out-of-office auto-acks are excluded.
                #
                # CRITICAL INVARIANT: this F() update and _execute_actions's
                # prospect.save() calls MUST touch disjoint columns. The
                # save() calls in _execute_actions currently all use
                # update_fields=[...] without 'reply_count' or
                # 'last_replied_at' — if anyone adds a plain save() there,
                # the F() increment will be silently clobbered. See the
                # docstring invariant note on _execute_actions.
                COUNTED_CLASSIFICATIONS = (
                    'interested', 'question', 'other',
                    'not_interested', 'opt_out',
                )
                if not is_system and classification in COUNTED_CLASSIFICATIONS:
                    Prospect.objects.filter(pk=prospect.pk).update(
                        reply_count=F('reply_count') + 1,
                        last_replied_at=inbound.created_at,
                        updated_at=timezone.now(),
                    )

                # Execute auto-actions (opt-out, bounce, not-interested, etc.)
                if not is_system:
                    self._execute_actions(prospect, inbound, classification)

                # Auto-reply if campaign has it enabled and template exists
                if (not is_system
                        and matched_campaign.auto_reply_enabled
                        and classification in ('interested', 'question')
                        and needs_reply):
                    self._try_auto_reply(prospect, inbound, matched_campaign, mailbox_obj)

                # G3 (2026-04-15): do NOT auto-mark needs_reply=True inbounds as
                # \Seen here. Leaving them UNSEEN in IMAP is the signal that the
                # human operator can still claim them by opening in their mail
                # client. handle_replies re-checks \Seen before AI reply and
                # marks \Seen only after successful send.
                #
                # System emails, opt-outs, bounces, not_interested, and
                # out_of_office get marked \Seen immediately because they
                # trigger suppression and do not need human review.
                if is_system or classification in (
                    'opt_out', 'bounce', 'not_interested', 'out_of_office',
                ):
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
        """Execute automated actions based on classification. No email sending.

        CRITICAL INVARIANT (2026-04-15 — H2):
            The caller has ALREADY applied an atomic F() update to
            `prospect.reply_count` and `prospect.last_replied_at` on
            this row immediately before calling this method. Every
            `prospect.save()` in here MUST pass `update_fields=[...]`
            with an explicit column list that DOES NOT include
            `reply_count` or `last_replied_at` — otherwise the F()
            increment will be silently clobbered by the stale
            in-memory values on the Prospect instance.

            If you need to change reply_count from inside this method,
            use another `Prospect.objects.filter(pk=prospect.pk).update(
            reply_count=...)` — never `prospect.save()` without
            update_fields.

            Enforced by convention, not by tests. Check every save()
            in this method before merging.
        """

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
