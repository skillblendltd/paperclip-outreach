"""Sprint 7 Phase 7.1.9 — shadow-mode decision preview.

Runs `next_action.decide_next_action()` against every prospect in a
campaign (or product) and prints what the executor WOULD do without
actually acting. Use this before flipping `use_context_assembler=True`
on a campaign to sanity-check the brain's routing.

Examples:
    python manage.py next_action_preview --campaign "TaggIQ Warm Re-engagement Apr 2026"
    python manage.py next_action_preview --product taggiq --limit 20
    python manage.py next_action_preview --product fullypromoted --summary
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from campaigns.models import Campaign, Prospect
from campaigns.services.brain import BrainNotFound
from campaigns.services.next_action import decide_next_action


class Command(BaseCommand):
    help = 'Preview next_action decisions for prospects without acting (shadow mode).'

    def add_arguments(self, parser):
        parser.add_argument('--campaign', help='Campaign name substring')
        parser.add_argument('--product', help='Product slug')
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--summary', action='store_true',
                            help='Print only the aggregate count breakdown')

    def handle(self, *args, **opts):
        qs = Prospect.objects.select_related('campaign__product_ref')
        if opts.get('campaign'):
            qs = qs.filter(campaign__name__icontains=opts['campaign'])
        if opts.get('product'):
            qs = qs.filter(campaign__product_ref__slug=opts['product'])
        qs = qs.order_by('-created_at')[:opts['limit']]

        total = 0
        channel_counts = Counter()
        reason_counts = Counter()
        errors = 0

        for p in qs:
            total += 1
            try:
                action = decide_next_action(p)
            except BrainNotFound as exc:
                errors += 1
                if not opts.get('summary'):
                    self.stdout.write(f'  ERR  {p.id} ({p.status}) -> no_brain: {exc}')
                continue
            channel_counts[action.channel or 'none'] += 1
            reason_counts[action.reason.split(':')[0]] += 1
            if not opts.get('summary'):
                name = (p.decision_maker_name or p.email or str(p.id))[:24]
                self.stdout.write(
                    f'  {(action.channel or "-"):5} | {p.status:15} | {name:24} '
                    f'| {action.reason[:60]}'
                )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Summary ==='))
        self.stdout.write(f'  total evaluated: {total}')
        self.stdout.write(f'  brain errors:    {errors}')
        self.stdout.write('  channels:')
        for ch, n in channel_counts.most_common():
            self.stdout.write(f'    {ch:10} {n}')
        self.stdout.write('  reasons (by family):')
        for reason, n in reason_counts.most_common():
            self.stdout.write(f'    {reason:25} {n}')
