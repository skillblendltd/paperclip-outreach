"""
Sync Google Calendar 1-2-1 bookings to prospect status.

Scans the prakash@fullypromoted.ie mailbox for signals that a 1-2-1 meeting
has been booked or completed, then updates the matching BNI prospect:
  - status -> engaged
  - send_enabled -> False
  - notes updated

Signal sources (checked in order):
  1. Fathom recap emails (from no-reply@fathom.video)
     Subject: 'Recap for "1-2-1 with Prakash(Fully Promoted) (First Last)"'
     -> Meeting definitely happened, highest confidence

  2. Google Calendar invitation emails (from calendar-noreply@google.com)
     Subject: 'New event: 1-2-1 with Prakash(Fully Promoted) (First Last)'
     -> Meeting booked, should suppress further sequences immediately

Matching strategy:
  - Extract name from subject -> split to first/last
  - Match against Prospect.decision_maker_name in FP BNI campaigns (case-insensitive)
  - Fall back to email extracted from body if name match fails

Run:
    python manage.py sync_calendar
    python manage.py sync_calendar --dry-run
    python manage.py sync_calendar --days 30   # look back N days (default 60)
"""

import email
import imaplib
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from campaigns.models import Campaign, InboundEmail, MailboxConfig, Prospect


class Command(BaseCommand):
    help = 'Sync BNI 1-2-1 meeting bookings from email to prospect status'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving changes')
        parser.add_argument('--days', type=int, default=60, help='Look back N days (default: 60)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days = options['days']
        since = datetime.now() - timedelta(days=days)
        since_str = since.strftime('%d-%b-%Y')

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] No changes will be saved.\n'))

        # Get the FP BNI mailbox config
        try:
            mb = MailboxConfig.objects.get(
                imap_email='prakash@fullypromoted.ie',
                campaign__name__icontains='BNI',
                is_active=True,
            )
        except MailboxConfig.DoesNotExist:
            self.stderr.write('FP BNI MailboxConfig not found.')
            return

        # Connect to IMAP
        self.stdout.write(f'Connecting to {mb.imap_host}...')
        imap = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port)
        imap.login(mb.imap_email, mb.imap_password)
        imap.select('"[Gmail]/All Mail"')
        self.stdout.write(self.style.SUCCESS(f'Connected to {mb.imap_email}'))

        meetings = []

        # --- Source 1: Fathom recaps ---
        meetings += self._scan_fathom(imap, since_str)

        # --- Source 2: Google Calendar booking notifications ---
        meetings += self._scan_google_calendar(imap, since_str)

        imap.logout()

        if not meetings:
            self.stdout.write('No 1-2-1 meeting signals found.')
            return

        self.stdout.write(f'\nFound {len(meetings)} meeting signal(s):')
        updated = 0
        already_done = 0

        for m in meetings:
            self.stdout.write(f'\n  [{m["source"]}] {m["name"]} | {m["date"]} | email={m.get("email", "?")}')
            prospect = self._find_prospect(m)
            if not prospect:
                self.stdout.write(self.style.WARNING('    -> No matching prospect found'))
                continue

            if not prospect.send_enabled and prospect.status in ('engaged', 'interested', 'demo_scheduled', 'design_partner'):
                self.stdout.write(f'    -> Already handled: {prospect.decision_maker_name} ({prospect.status})')
                already_done += 1
                continue

            self.stdout.write(self.style.SUCCESS(
                f'    -> Match: {prospect.decision_maker_name} <{prospect.email}> '
                f'| {prospect.campaign.name} | {prospect.status} -> engaged'
            ))

            if not dry_run:
                old_status = prospect.status
                prospect.status = 'engaged'
                prospect.send_enabled = False
                note = (
                    f'[{m["date"]}] 1-2-1 meeting detected via {m["source"]}. '
                    f'Status: {old_status} -> engaged. Sending disabled.'
                )
                prospect.notes = (prospect.notes or '') + f' | {note}'
                prospect.save(update_fields=['status', 'send_enabled', 'notes', 'updated_at'])
                updated += 1

        self.stdout.write(f'\n{"=" * 50}')
        self.stdout.write(f'Updated: {updated} | Already handled: {already_done}')
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] No changes were saved.'))

    def _scan_fathom(self, imap, since_str):
        """Scan for Fathom recap emails - highest confidence a meeting happened."""
        meetings = []
        status, data = imap.search(None, 'FROM', 'fathom.video', 'SINCE', since_str)
        msg_ids = data[0].split() if data[0] else []
        self.stdout.write(f'Fathom recap emails since {since_str}: {len(msg_ids)}')

        for mid in msg_ids:
            try:
                status, msg_data = imap.fetch(mid, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                subject = msg.get('Subject', '')

                # Match: 'Recap for "1-2-1 with Prakash(Fully Promoted) (First Last)"'
                # or:    'Recap for "1-2-1 with Prakash(Fully Promoted) (First)"'
                m = re.search(
                    r'1-2-1 with Prakash\(?Fully Promoted\)?\s*\(([^)]+)\)',
                    subject, re.IGNORECASE
                )
                if not m:
                    continue

                name = m.group(1).strip()
                date_str = msg.get('Date', '')
                try:
                    dt = parsedate_to_datetime(date_str)
                    date = dt.strftime('%Y-%m-%d')
                except Exception:
                    date = 'unknown'

                meetings.append({
                    'source': 'Fathom',
                    'name': name,
                    'date': date,
                    'email': self._extract_attendee_email(msg),
                })
            except Exception as e:
                self.stderr.write(f'  Error parsing Fathom email {mid}: {e}')

        return meetings

    def _scan_google_calendar(self, imap, since_str):
        """Scan for Google Calendar booking notification emails."""
        meetings = []

        # Search for calendar booking notifications
        status, data = imap.search(
            None, 'FROM', 'calendar-noreply@google.com', 'SINCE', since_str
        )
        msg_ids = data[0].split() if data[0] else []
        self.stdout.write(f'Google Calendar notification emails since {since_str}: {len(msg_ids)}')

        for mid in msg_ids:
            try:
                status, msg_data = imap.fetch(mid, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                subject = msg.get('Subject', '')

                # Match new booking: 'New event: 1-2-1 with Prakash(Fully Promoted) (Name)'
                m = re.search(
                    r'1-2-1 with Prakash\(?Fully Promoted\)?\s*\(([^)]+)\)',
                    subject, re.IGNORECASE
                )
                if not m:
                    continue

                name = m.group(1).strip()
                date_str = msg.get('Date', '')
                try:
                    dt = parsedate_to_datetime(date_str)
                    date = dt.strftime('%Y-%m-%d')
                except Exception:
                    date = 'unknown'

                meetings.append({
                    'source': 'Google Calendar',
                    'name': name,
                    'date': date,
                    'email': self._extract_attendee_email(msg),
                })
            except Exception as e:
                self.stderr.write(f'  Error parsing Calendar email {mid}: {e}')

        return meetings

    def _extract_attendee_email(self, msg):
        """Extract external attendee email from email body."""
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                        break
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
            except Exception:
                pass

        # If no plain text, try HTML
        if not body and msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                        body = re.sub(r'<[^>]+>', ' ', body)
                        break
                    except Exception:
                        pass

        # Find external emails (not @fullypromoted.ie, @taggiq.com, @google.com)
        skip_domains = ('fullypromoted', 'taggiq', 'google', 'fathom', 'calendar')
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', body)
        for e in emails:
            if not any(d in e.lower() for d in skip_domains):
                return e.lower()
        return None

    def _find_prospect(self, meeting):
        """Find matching prospect from meeting name/email across FP BNI campaigns."""
        # BNI campaigns only
        bni_campaigns = Campaign.objects.filter(
            product='fullypromoted',
            name__icontains='BNI',
        )

        name = meeting.get('name', '')
        attendee_email = meeting.get('email')

        # 1. Try email match first (most reliable)
        if attendee_email:
            p = Prospect.objects.filter(
                email__iexact=attendee_email,
                campaign__in=bni_campaigns,
            ).first()
            if p:
                return p

        # 2. Try full name match against decision_maker_name (case-insensitive)
        if name:
            p = Prospect.objects.filter(
                decision_maker_name__iexact=name,
                campaign__in=bni_campaigns,
            ).first()
            if p:
                return p

            # 3. Try business_name contains full name (BNI data often stores full name as business_name)
            p = Prospect.objects.filter(
                business_name__icontains=name,
                campaign__in=bni_campaigns,
            ).first()
            if p:
                return p

            # 4. Try last name against business_name + first name against decision_maker_name
            parts = name.split()
            if len(parts) >= 2:
                first_name, last_name = parts[0], parts[-1]
                qs = Prospect.objects.filter(
                    decision_maker_name__icontains=first_name,
                    business_name__icontains=last_name,
                    campaign__in=bni_campaigns,
                )
                if qs.count() == 1:
                    return qs.first()
                # Also try just last name in business_name
                qs2 = Prospect.objects.filter(
                    business_name__icontains=last_name,
                    campaign__in=bni_campaigns,
                )
                if qs2.count() == 1:
                    return qs2.first()

            # 5. Try first name only (if unique in BNI campaigns)
            first_name = parts[0] if parts else ''
            if first_name:
                qs = Prospect.objects.filter(
                    decision_maker_name__icontains=first_name,
                    campaign__in=bni_campaigns,
                )
                if qs.count() == 1:
                    return qs.first()

        return None
