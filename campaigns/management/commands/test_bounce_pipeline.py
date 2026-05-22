"""
Test command to verify the bounce/complaint auto-suppression pipeline.

Usage:
  python manage.py test_bounce_pipeline
  python manage.py test_bounce_pipeline --send-test-email
  python manage.py test_bounce_pipeline --simulate-bounce
"""
import json
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from campaigns.models import Suppression, Product, Organization, Campaign, Prospect, EmailLog
from campaigns.email_service import EmailService
from campaigns.services.eligibility import is_suppressed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test the SES bounce/complaint auto-suppression pipeline'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-test-email',
            action='store_true',
            help='Send a test email to SES bounce simulator'
        )
        parser.add_argument(
            '--simulate-bounce',
            action='store_true',
            help='Simulate a bounce event (for local testing without SES)'
        )
        parser.add_argument(
            '--check-suppressions',
            action='store_true',
            help='List current suppressions'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== SES Bounce Pipeline Test ===\n'))

        if options['check_suppressions']:
            self.check_suppressions()
        elif options['send_test_email']:
            self.send_test_email()
        elif options['simulate_bounce']:
            self.simulate_bounce()
        else:
            self.run_diagnostics()

    def run_diagnostics(self):
        """Run full diagnostics on the pipeline."""
        self.stdout.write('Running pipeline diagnostics...\n')

        # 1. Check configuration
        self.stdout.write(self.style.HTTP_INFO('Step 1: Configuration Check'))
        config_set = getattr(settings, 'AWS_SES_CONFIGURATION_SET', '')
        if config_set:
            self.stdout.write(f'  ✓ AWS_SES_CONFIGURATION_SET: {config_set}')
        else:
            self.stdout.write(self.style.WARNING(
                '  ✗ AWS_SES_CONFIGURATION_SET not configured. '
                'Bounces/complaints will not trigger Lambda.'
            ))

        # 2. Check database models
        self.stdout.write(self.style.HTTP_INFO('\nStep 2: Database Models'))
        try:
            # Check Suppression model has all required fields
            suppression_fields = [f.name for f in Suppression._meta.fields]
            required_fields = ['email', 'product', 'reason', 'soft_bounce_count', 'notes']
            for field in required_fields:
                if field in suppression_fields:
                    self.stdout.write(f'  ✓ Suppression.{field}')
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Suppression.{field} missing'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Error checking models: {e}'))

        # 3. Check suppression storage
        self.stdout.write(self.style.HTTP_INFO('\nStep 3: Suppression Storage'))
        total_suppressions = Suppression.objects.count()
        self.stdout.write(f'  Total suppressions: {total_suppressions}')

        by_reason = Suppression.objects.values('reason').annotate(
            count=Count('id')
        ).order_by('-count')
        for row in by_reason:
            self.stdout.write(f'    - {row["reason"]}: {row["count"]}')

        # 4. Test product-scoped suppression
        self.stdout.write(self.style.HTTP_INFO('\nStep 4: Product-Scoped Suppression'))
        try:
            org = Organization.objects.first()
            if org:
                products = org.products.all()
                for product in products:
                    count = product.suppressions.count()
                    global_count = Suppression.objects.filter(
                        email__in=[s.email for s in product.suppressions.all()],
                        product__isnull=True
                    ).count()
                    self.stdout.write(f'  {product.slug}:')
                    self.stdout.write(f'    - Product-scoped: {count}')
                    self.stdout.write(f'    - Global: {global_count}')
            else:
                self.stdout.write('  No organizations found')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error: {e}'))

        # 5. Test is_suppressed function
        self.stdout.write(self.style.HTTP_INFO('\nStep 5: is_suppressed Function'))
        try:
            org = Organization.objects.first()
            if org:
                product = org.products.first()
                if product:
                    # Find a suppressed email
                    supp = product.suppressions.first()
                    if supp:
                        result = is_suppressed(supp.email, product)
                        if result:
                            self.stdout.write(f'  ✓ is_suppressed("{supp.email}") = True')
                        else:
                            self.stdout.write(self.style.ERROR(
                                f'  ✗ is_suppressed("{supp.email}") returned False, expected True'
                            ))
                    else:
                        self.stdout.write('  No suppressions found for testing')
                else:
                    self.stdout.write('  No products found')
            else:
                self.stdout.write('  No organizations found')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error: {e}'))

        self.stdout.write(self.style.SUCCESS('\n✓ Diagnostics complete\n'))

    def send_test_email(self):
        """Send a test email to SES bounce simulator."""
        self.stdout.write('Sending test email to SES bounce simulator...')

        try:
            # Get first campaign
            campaign = Campaign.objects.filter(sending_enabled=True).first()
            if not campaign:
                self.stdout.write(self.style.ERROR('No active campaign found'))
                return

            # Create test prospect
            prospect = Prospect.objects.create(
                campaign=campaign,
                business_name='Test Company',
                email='bounce@simulator.amazonses.com',  # SES bounce simulator
                send_enabled=True,
                status='new',
            )

            self.stdout.write(f'Created test prospect: {prospect.business_name}')
            self.stdout.write(f'Email: {prospect.email}')

            # Send email
            result = EmailService.send_email(
                to_emails=[prospect.email],
                subject='Test Email for Bounce Simulator',
                body_html='<p>This is a test email to trigger a bounce.</p><p>Sent at: ' + str(timezone.now()) + '</p>',
                from_email=campaign.from_email,
                from_name=campaign.from_name,
            )

            self.stdout.write(self.style.SUCCESS(f'Email sent: {result}'))
            self.stdout.write(self.style.WARNING(
                'Note: SES bounce simulator requires the email to be sent via SES '
                '(not console mode) to trigger a bounce notification.'
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))

    def simulate_bounce(self):
        """Simulate a bounce event locally (for testing Lambda without actual SES)."""
        self.stdout.write('Simulating bounce event...')

        try:
            # Manually create a suppression as if Lambda had processed a bounce
            org = Organization.objects.first()
            if not org:
                self.stdout.write(self.style.ERROR('No organization found'))
                return

            product = org.products.first()
            if not product:
                self.stdout.write(self.style.ERROR(f'No products in {org.name}'))
                return

            email = 'simulated-bounce@example.com'

            # Create hard bounce suppression (as Lambda would)
            supp, created = Suppression.objects.get_or_create(
                email=email,
                product=product,
                defaults={'reason': 'hard_bounce', 'notes': 'Simulated bounce for testing'}
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f'Created suppression: {supp.email}'))
            else:
                self.stdout.write(f'Suppression already exists: {supp.email}')

            # Verify is_suppressed works
            is_supp = is_suppressed(email, product)
            self.stdout.write(f'is_suppressed("{email}") = {is_supp}')

            if is_supp:
                self.stdout.write(self.style.SUCCESS('✓ Suppression verified'))
            else:
                self.stdout.write(self.style.ERROR('✗ Suppression check failed'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))

    def check_suppressions(self):
        """List current suppressions."""
        self.stdout.write('Current suppressions:')

        suppressions = Suppression.objects.all().order_by('-created_at')

        if not suppressions.exists():
            self.stdout.write('  (none)')
            return

        for supp in suppressions[:20]:  # Show last 20
            product_scope = supp.product.slug if supp.product else 'GLOBAL'
            self.stdout.write(f'  {supp.email}')
            self.stdout.write(f'    Reason: {supp.reason}')
            self.stdout.write(f'    Product: {product_scope}')
            if supp.soft_bounce_count > 0:
                self.stdout.write(f'    Soft bounces: {supp.soft_bounce_count}')
            if supp.notes:
                self.stdout.write(f'    Notes: {supp.notes}')
            self.stdout.write('')


# Import Count at the top
from django.db.models import Count
from django.utils import timezone
