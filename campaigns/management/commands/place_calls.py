"""
Place outbound calls for campaigns with calling_enabled=True.
Run daily via cron or manually: python manage.py place_calls
"""
import time
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from campaigns.models import Campaign, Prospect, CallLog
from campaigns.call_service import CallService
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Place outbound calls for active calling campaigns'

    def add_arguments(self, parser):
        parser.add_argument('--campaign', type=str, help='Campaign name (optional, defaults to all)')
        parser.add_argument('--limit', type=int, default=0, help='Max calls to place (0=use campaign limit)')
        parser.add_argument('--dry-run', action='store_true', help='Preview calls without placing them')

    def handle(self, *args, **options):
        campaign_name = options.get('campaign')
        limit = options.get('limit')
        dry_run = options.get('dry_run', False)

        # Get campaigns with calling enabled
        campaigns = Campaign.objects.filter(calling_enabled=True)
        if campaign_name:
            campaigns = campaigns.filter(name__icontains=campaign_name)

        if not campaigns.exists():
            self.stdout.write('No campaigns with calling enabled.')
            return

        total_placed = 0

        for campaign in campaigns:
            self.stdout.write(f'\n=== {campaign.name} ===')

            assistant_id = campaign.vapi_assistant_id or settings.VAPI_ASSISTANT_ID
            phone_number_id = settings.VAPI_PHONE_NUMBER_ID

            if not assistant_id:
                self.stdout.write(self.style.WARNING(f'  No assistant ID configured, skipping'))
                continue

            # How many calls already placed today for this campaign?
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            calls_today = CallLog.objects.filter(
                campaign=campaign,
                created_at__gte=today_start,
            ).count()

            remaining = campaign.max_calls_per_day - calls_today
            if remaining <= 0:
                self.stdout.write(f'  Daily limit reached ({calls_today}/{campaign.max_calls_per_day})')
                continue

            # Apply manual limit if set
            if limit > 0:
                remaining = min(remaining, limit - total_placed)

            if remaining <= 0:
                break

            # Find eligible prospects:
            # - has phone number
            # - send_enabled
            # - not opted out, not interested, not do-not-call
            # - calls_sent < max_calls_per_prospect
            # - not called in last 24 hours (min gap)
            min_gap_cutoff = timezone.now() - timedelta(minutes=campaign.min_gap_call_minutes)

            eligible = Prospect.objects.filter(
                campaign=campaign,
                send_enabled=True,
                phone__gt='',  # has phone
                calls_sent__lt=campaign.max_calls_per_prospect,
            ).exclude(
                status__in=['opted_out', 'not_interested', 'demo_scheduled', 'design_partner'],
            ).exclude(
                last_called_at__gte=min_gap_cutoff,
            ).order_by('-score', '-tier')[:remaining]

            self.stdout.write(f'  Eligible prospects: {eligible.count()} (placing up to {remaining})')

            for prospect in eligible:
                if dry_run:
                    self.stdout.write(f'  [DRY RUN] Would call: {prospect.phone} ({prospect.business_name})')
                    total_placed += 1
                    continue

                # Place call
                result = CallService.place_call(
                    phone_number=prospect.phone,
                    assistant_id=assistant_id,
                    phone_number_id=phone_number_id,
                    prospect_name=prospect.decision_maker_name or '',
                    company_name=prospect.business_name,
                    segment=prospect.segment,
                    metadata={'prospect_id': str(prospect.id), 'campaign_id': str(campaign.id)},
                )

                # Log the call
                call_log = CallLog.objects.create(
                    campaign=campaign,
                    prospect=prospect,
                    phone_number=prospect.phone,
                    vapi_call_id=result.get('call_id', ''),
                    status='placed' if result['success'] else 'failed',
                    triggered_by='management_command',
                )

                if result['success']:
                    # Update prospect
                    prospect.calls_sent += 1
                    prospect.last_called_at = timezone.now()
                    if prospect.status == 'new':
                        prospect.status = 'contacted'
                    prospect.save(update_fields=['calls_sent', 'last_called_at', 'status'])

                    self.stdout.write(self.style.SUCCESS(
                        f'  ✓ Called {prospect.phone} ({prospect.business_name}) — call_id: {result["call_id"]}'
                    ))
                    total_placed += 1
                else:
                    self.stdout.write(self.style.ERROR(
                        f'  ✗ Failed {prospect.phone} ({prospect.business_name}): {result["error"][:100]}'
                    ))

                # Rate limiting
                time.sleep(max(campaign.min_gap_call_minutes * 60, 5))

        self.stdout.write(f'\nDone. Total calls placed: {total_placed}')
