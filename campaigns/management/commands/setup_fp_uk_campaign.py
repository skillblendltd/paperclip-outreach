"""
Create Fully Promoted UK organization, product, and campaign for design partner launch.
"""
from django.core.management.base import BaseCommand
from campaigns.models import Organization, Product, Campaign


class Command(BaseCommand):
    help = 'Setup FP UK multi-tenant campaign'

    def handle(self, *args, **options):
        # Create Organization
        org, org_created = Organization.objects.get_or_create(
            slug='fully-promoted-uk',
            defaults={
                'name': 'Fully Promoted UK',
                'is_active': True,
            }
        )
        status = 'created' if org_created else 'existing'
        self.stdout.write(f'✓ Organization: {org.name} ({status})')

        # Create Product
        product, prod_created = Product.objects.get_or_create(
            organization=org,
            slug='fp-uk-franchise',
            defaults={
                'name': 'Fully Promoted UK Franchise Recruitment',
                'is_active': True,
            }
        )
        status = 'created' if prod_created else 'existing'
        self.stdout.write(f'✓ Product: {product.name} ({status})')

        # Create Campaign (DRAFT mode)
        campaign, camp_created = Campaign.objects.get_or_create(
            name='UK Partner Search',
            product_ref=product,
            defaults={
                'from_email': 'jamal@fullypromoted.co.uk',
                'from_name': 'Jamal Shah',
                'sending_enabled': False,
                'max_emails_per_day': 15,
                'min_gap_minutes': 1440,  # 24 hours
                'max_emails_per_prospect': 5,
            }
        )
        status = 'created' if camp_created else 'existing'
        self.stdout.write(f'✓ Campaign: {campaign.name} ({status})')

        self.stdout.write(self.style.SUCCESS('\n📊 FP UK Campaign Setup Complete'))
        self.stdout.write(f'  Organization ID: {org.id}')
        self.stdout.write(f'  Product ID: {product.id}')
        self.stdout.write(f'  Campaign ID: {campaign.id}')
        self.stdout.write(f'  Status: DRAFT (sending_enabled=False)')
        self.stdout.write(f'  From: {campaign.from_email}')
        self.stdout.write(f'\n✓ Ready for: prospect import → email templates → reply automation')
