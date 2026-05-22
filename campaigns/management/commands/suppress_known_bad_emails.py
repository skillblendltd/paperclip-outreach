"""
One-time management command to suppress obviously bad test/placeholder emails.
Run this once after deploying email validation to catch any bad addresses
already in the database.

Usage: python manage.py suppress_known_bad_emails
"""
import logging
from django.core.management.base import BaseCommand
from campaigns.models import Prospect, Suppression
from campaigns.utils import is_likely_test_email

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Suppress known bad test/placeholder emails already in the database'

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)

        # Find all prospects with test email addresses
        bad_count = 0
        skip_count = 0

        for prospect in Prospect.objects.all():
            if not prospect.email:
                continue

            if is_likely_test_email(prospect.email):
                # Add to suppression list for their product
                product = prospect.campaign.product_ref
                if product:
                    suppression, created = Suppression.objects.get_or_create(
                        product=product,
                        email=prospect.email,
                        defaults={'reason': 'test_address'}
                    )
                    if created:
                        bad_count += 1
                        if verbosity >= 2:
                            self.stdout.write(f'Suppressed: {prospect.email}')
                    else:
                        skip_count += 1
                else:
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Skipped {prospect.email} - no product_ref on campaign'
                            )
                        )
                    skip_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuppression complete:\n'
                f'  Newly suppressed: {bad_count}\n'
                f'  Already suppressed: {skip_count}'
            )
        )
