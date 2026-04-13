"""List flagged inbound emails ready for AI reply.

Replaces the inline Django shell block that used to live in every reply
PromptTemplate (Step 1 of the execution recipe). Org-agnostic - any persona
prompt can call this with its own product slug.

Usage:
    python manage.py list_pending_replies --product-slug print-promo
    python manage.py list_pending_replies --product-slug taggiq --limit 20
    python manage.py list_pending_replies --product-slug print-promo --max-attempts 5
"""
from django.core.management.base import BaseCommand

from campaigns.models import InboundEmail


class Command(BaseCommand):
    help = 'Print flagged inbound emails ready for AI reply, scoped to a product slug'

    def add_arguments(self, parser):
        parser.add_argument(
            '--product-slug', required=True,
            help='Product slug to filter by (e.g. print-promo, taggiq, fullypromoted)',
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Max inbounds to print (0 = no limit)',
        )
        parser.add_argument(
            '--max-attempts', type=int, default=5,
            help='Skip inbounds whose ai_attempt_count >= this value (default 5)',
        )

    def handle(self, *args, **options):
        slug = options['product_slug']
        limit = options['limit']
        max_attempts = options['max_attempts']

        qs = InboundEmail.objects.filter(
            needs_reply=True,
            replied=False,
            campaign__isnull=False,
            campaign__product_ref__slug=slug,
            ai_attempt_count__lt=max_attempts,
        ).select_related('prospect', 'campaign').order_by('received_at')

        if limit:
            qs = qs[:limit]

        count = qs.count() if not limit else len(list(qs))
        if count == 0:
            self.stdout.write(f'No pending inbounds for product "{slug}".')
            return

        self.stdout.write(f'=== {count} pending inbound(s) for product "{slug}" ===\n')

        for ie in qs:
            p = ie.prospect
            self.stdout.write('=' * 70)
            self.stdout.write(f'ID: {ie.id}')
            self.stdout.write(f'From: {ie.from_name or "-"} <{ie.from_email}>')
            if p:
                self.stdout.write(f'Name: {p.decision_maker_name or "-"} | Business: {p.business_name or "-"}')
                self.stdout.write(f'Status: {p.status} | City: {p.city or "-"}')
                if p.notes:
                    self.stdout.write(f'Notes: {p.notes[:200]}')
            self.stdout.write(f'Campaign: {ie.campaign.name}')
            self.stdout.write(f'Classification: {ie.classification}')
            self.stdout.write(f'Subject: {ie.subject}')
            self.stdout.write(f'Message-ID: {ie.message_id}')
            self.stdout.write(f'In-Reply-To: {ie.in_reply_to or "-"}')
            self.stdout.write(f'Attempts so far: {ie.ai_attempt_count}/{max_attempts}')
            self.stdout.write('---')
            self.stdout.write((ie.body_text or '')[:2000])
            self.stdout.write('')
