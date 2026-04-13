"""Sprint 7 Phase 7.3.4 — per-campaign KPI rollup.

Pure read. Prints for one or more campaigns matched by name substring:
  - prospects touched
  - emails sent
  - inbound replies received
  - interested %
  - demos scheduled
  - escalations (ESCALATION: lines in prospect.notes)
  - total AI cost (sum AIUsageLog.cost_usd)
  - cost / demo
  - cost / prospect touched

Usage:
    python manage.py campaign_kpis --campaign "Warm Re-engagement"
    python manage.py campaign_kpis --campaign "Kingswood"
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum

from campaigns.models import (
    Campaign, Prospect, EmailLog, InboundEmail, AIUsageLog,
)


class Command(BaseCommand):
    help = 'Print KPI rollup for campaigns matching --campaign name substring'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign', required=True,
            help='Campaign name substring (case-insensitive)',
        )

    def handle(self, *args, **options):
        name_sub = options['campaign']
        campaigns = Campaign.objects.filter(name__icontains=name_sub)
        if not campaigns.exists():
            self.stderr.write(self.style.ERROR(f'No campaigns match "{name_sub}"'))
            return

        for campaign in campaigns:
            self._print_campaign_kpis(campaign)

    def _print_campaign_kpis(self, campaign):
        prospects = Prospect.objects.filter(campaign=campaign)
        total_prospects = prospects.count()
        touched = prospects.filter(emails_sent__gt=0).count()

        emails_sent = EmailLog.objects.filter(
            campaign=campaign, status='sent',
        ).count()
        replies = InboundEmail.objects.filter(campaign=campaign).count()

        interested = prospects.filter(status='interested').count()
        demos = prospects.filter(status='demo_scheduled').count()
        design_partners = prospects.filter(status='design_partner').count()

        # Escalations — count ESCALATION: markers in notes.
        escalations = 0
        for notes in prospects.exclude(notes='').values_list('notes', flat=True):
            if notes:
                escalations += notes.count('ESCALATION:')

        cost_agg = AIUsageLog.objects.filter(campaign=campaign).aggregate(
            total=Sum('cost_usd'),
        )
        total_cost = cost_agg['total'] or Decimal('0')

        pct_interested = (interested / touched * 100) if touched else 0.0
        cost_per_demo = (total_cost / demos) if demos else None
        cost_per_touched = (total_cost / touched) if touched else None

        self.stdout.write('')
        self.stdout.write(f'=== {campaign.name} ===')
        self.stdout.write(f'  product:            {campaign.product_ref.slug if campaign.product_ref else "-"}')
        self.stdout.write(f'  flag (contextual):  {getattr(campaign, "use_context_assembler", False)}')
        self.stdout.write(f'  prospects total:    {total_prospects}')
        self.stdout.write(f'  prospects touched:  {touched}')
        self.stdout.write(f'  emails sent:        {emails_sent}')
        self.stdout.write(f'  replies received:   {replies}')
        self.stdout.write(f'  interested:         {interested} ({pct_interested:.1f}% of touched)')
        self.stdout.write(f'  demo_scheduled:     {demos}')
        self.stdout.write(f'  design_partner:     {design_partners}')
        self.stdout.write(f'  escalations:        {escalations}')
        self.stdout.write(f'  total AI cost:      ${total_cost:.4f}')
        if cost_per_demo is not None:
            self.stdout.write(f'  cost / demo:        ${cost_per_demo:.4f}')
        else:
            self.stdout.write('  cost / demo:        n/a (0 demos)')
        if cost_per_touched is not None:
            self.stdout.write(f'  cost / touched:     ${cost_per_touched:.4f}')
        else:
            self.stdout.write('  cost / touched:     n/a (0 touched)')
