"""
Universal sender command. Replaces 18 separate sender scripts with one DB-driven command.

Usage:
    python manage.py send_sequences                      # All active campaigns
    python manage.py send_sequences --product taggiq     # One product
    python manage.py send_sequences --campaign "BNI"     # Name substring
    python manage.py send_sequences --dry-run            # Preview only
    python manage.py send_sequences --status             # Show eligible counts only
    python manage.py send_sequences --limit 5            # Max per campaign

Safe to run multiple times - duplicate sequence check prevents double-sends.
"""
import random
import time
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand

from campaigns.models import Campaign
from campaigns.services.eligibility import get_eligible_prospects
from campaigns.services.safeguards import daily_remaining, check_min_gap
from campaigns.services.template_resolver import get_template
from campaigns.services.send_orchestrator import send_one


class Command(BaseCommand):
    help = 'Send due sequence emails across all active campaigns (replaces 18 sender scripts)'

    def add_arguments(self, parser):
        parser.add_argument('--product', help='Filter by product slug (e.g. taggiq, fullypromoted)')
        parser.add_argument('--exclude-product', help='Exclude this product slug')
        parser.add_argument('--campaign', help='Filter by campaign name substring')
        parser.add_argument('--exclude-campaign', help='Exclude campaigns whose name contains this substring')
        parser.add_argument('--dry-run', action='store_true', help='Preview without sending')
        parser.add_argument('--status', action='store_true', help='Show eligible counts only, do not send')
        parser.add_argument('--limit', type=int, default=0, help='Max sends per campaign (0=use campaign batch_size)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        status_only = options['status']
        product_filter = options.get('product')
        exclude_product = options.get('exclude_product')
        campaign_filter = options.get('campaign')
        exclude_campaign = options.get('exclude_campaign')
        limit_override = options['limit']

        # Get active campaigns
        qs = Campaign.objects.filter(
            sending_enabled=True,
            product_ref__is_active=True,
            product_ref__organization__is_active=True,
        ).select_related('product_ref__organization')

        if product_filter:
            qs = qs.filter(product_ref__slug=product_filter)
        if exclude_product:
            qs = qs.exclude(product_ref__slug=exclude_product)
        if campaign_filter:
            qs = qs.filter(name__icontains=campaign_filter)
        if exclude_campaign:
            qs = qs.exclude(name__icontains=exclude_campaign)

        campaigns = list(qs)
        if not campaigns:
            self.stdout.write(self.style.WARNING('No active campaigns found matching filters.'))
            return

        total_sent = 0
        total_skipped = 0
        total_failed = 0

        for campaign in campaigns:
            self.stdout.write(f'\n{"=" * 60}')
            product_slug = campaign.product_ref.slug if campaign.product_ref else campaign.product
            self.stdout.write(f'Campaign: {campaign.name} [{product_slug}]')
            self.stdout.write(f'{"=" * 60}')

            # Check send window
            if not self._is_within_window(campaign):
                self.stdout.write(self.style.WARNING('  Outside send window - skipping'))
                continue

            # Check daily remaining
            remaining = daily_remaining(campaign)
            if remaining <= 0:
                self.stdout.write(self.style.WARNING(f'  Daily limit reached - skipping'))
                continue

            self.stdout.write(f'  Daily remaining: {remaining}')

            # Get eligible prospects
            eligible = get_eligible_prospects(campaign)
            if not eligible:
                self.stdout.write('  No eligible prospects')
                continue

            # Sort by priority cities then score
            eligible = self._sort_prospects(eligible, campaign)

            # Apply batch limit
            batch_limit = limit_override or campaign.batch_size
            batch = eligible[:min(batch_limit, remaining)]

            self.stdout.write(f'  Eligible: {len(eligible)} | Batch: {len(batch)}')

            if status_only:
                # Show breakdown by sequence
                by_seq = {}
                for p, seq in eligible:
                    by_seq[seq] = by_seq.get(seq, 0) + 1
                for seq, count in sorted(by_seq.items()):
                    self.stdout.write(f'    Seq {seq}: {count} prospects')
                continue

            # Send
            campaign_sent = 0
            campaign_skipped = 0
            campaign_failed = 0

            # Sprint 7 Phase 7.2.4 — flag=True path consults channel_timing
            # before each send. Skip with a reason log and don't count toward
            # caps. Flag=False path untouched.
            flag_on = getattr(campaign, 'use_context_assembler', False)

            for prospect, seq_num in batch:
                if flag_on:
                    from campaigns.services.channel_timing import can_send_email
                    can, why = can_send_email(prospect)
                    if not can:
                        self.stdout.write(f'  skip (timing): {prospect.email} — {why}')
                        continue
                template = get_template(campaign, seq_num, prospect)
                if not template:
                    self.stdout.write(self.style.WARNING(
                        f'  No template for seq {seq_num} - skipping {prospect.business_name}'
                    ))
                    campaign_skipped += 1
                    continue

                result = send_one(campaign, prospect, template, seq_num, dry_run=dry_run)

                if result['status'] == 'sent':
                    campaign_sent += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  SENT [{seq_num}{result["variant"]}] {result["email"]} - {result["subject"][:50]}'
                    ))
                elif result['status'] == 'dry_run':
                    campaign_sent += 1
                    self.stdout.write(
                        f'  [DRY] [{seq_num}{result["variant"]}] {result["email"]} - {result["subject"][:50]}'
                    )
                elif result['status'] == 'failed':
                    campaign_failed += 1
                    self.stderr.write(self.style.ERROR(
                        f'  FAILED {result["email"]}: {result["error"]}'
                    ))
                else:
                    campaign_skipped += 1

                # Delay between sends (skip for dry run)
                if not dry_run and result['status'] == 'sent':
                    delay = random.randint(
                        campaign.inter_send_delay_min,
                        campaign.inter_send_delay_max,
                    )
                    time.sleep(delay)

            self.stdout.write(
                f'  Summary: sent={campaign_sent} skipped={campaign_skipped} failed={campaign_failed}'
            )
            total_sent += campaign_sent
            total_skipped += campaign_skipped
            total_failed += campaign_failed

        # Grand total
        self.stdout.write(f'\n{"=" * 60}')
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}TOTAL: sent={total_sent} skipped={total_skipped} failed={total_failed}'
        ))

    def _is_within_window(self, campaign):
        """Check if current time is within the campaign's send window."""
        try:
            tz = pytz.timezone(campaign.send_window_timezone)
        except pytz.UnknownTimeZoneError:
            return True  # Unknown timezone = don't block

        now = datetime.now(tz)
        allowed_days = [int(d.strip()) for d in campaign.send_window_days.split(',') if d.strip()]

        if now.weekday() not in allowed_days:
            return False
        if not (campaign.send_window_start_hour <= now.hour < campaign.send_window_end_hour):
            return False
        return True

    def _sort_prospects(self, eligible, campaign):
        """Sort eligible prospects by priority cities then score."""
        priority = set()
        if campaign.priority_cities:
            priority = {c.strip().lower() for c in campaign.priority_cities.split(',') if c.strip()}

        def sort_key(item):
            prospect, seq = item
            city_priority = 0 if prospect.city.lower() in priority else 1
            return (city_priority, -prospect.score)

        return sorted(eligible, key=sort_key)
