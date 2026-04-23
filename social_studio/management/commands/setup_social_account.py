"""
Interactive setup for social media accounts.

Creates a SocialAccount record with credentials for any supported platform.
For Facebook/Instagram, guides through the token exchange. For Google Business,
accepts a service account token.

Usage:
    python manage.py setup_social_account --product fullypromoted --platform facebook
    python manage.py setup_social_account --product fullypromoted --platform instagram
    python manage.py setup_social_account --product fullypromoted --platform google
    python manage.py setup_social_account --product taggiq --platform linkedin
"""
from django.core.management.base import BaseCommand, CommandError

from campaigns.models import Product
from social_studio.models import SocialAccount


SETUP_GUIDES = {
    'facebook': """
Facebook Page Setup
===================
1. Go to developers.facebook.com -> your app -> Tools -> Graph API Explorer
2. Select your Page, request permissions: pages_manage_posts, pages_read_engagement
3. Generate a Page Access Token
4. Exchange for a long-lived token:
   GET /oauth/access_token?grant_type=fb_exchange_token
     &client_id=YOUR_APP_ID
     &client_secret=YOUR_APP_SECRET
     &fb_exchange_token=SHORT_LIVED_TOKEN
5. Get your Page ID: GET /me/accounts (find the page, copy 'id')
""",
    'instagram': """
Instagram Business Account Setup
=================================
1. Your Instagram account must be a Business account linked to a Facebook Page
2. Use the same Facebook App and Page Access Token as Facebook
3. Get your IG Business Account ID:
   GET /{facebook_page_id}?fields=instagram_business_account
   Copy the 'id' from instagram_business_account
4. Required permissions: instagram_basic, instagram_content_publish
""",
    'google': """
Google Business Profile Setup
==============================
1. Go to console.cloud.google.com -> create or select project
2. Enable 'Google My Business API'
3. Create OAuth2 credentials (Desktop app type)
4. Run the OAuth flow to get an access token + refresh token
5. Get your location path:
   GET https://mybusinessaccountmanagement.googleapis.com/v1/accounts
   Then: GET /v1/accounts/{id}/locations
   Format: accounts/ACCOUNT_ID/locations/LOCATION_ID
""",
    'linkedin': """
LinkedIn Company Page Setup
============================
1. Go to linkedin.com/developers -> your app
2. Requires Community Management API approval (w_organization_social)
3. Generate an OAuth2 access token with scope: w_organization_social
4. Get your Organization ID from your company page URL or admin settings
""",
}


class Command(BaseCommand):
    help = 'Interactive setup for social media accounts (Facebook, Instagram, Google, LinkedIn)'

    def add_arguments(self, parser):
        parser.add_argument('--product', type=str, required=True, help='Product slug')
        parser.add_argument('--platform', type=str, required=True,
                            choices=['facebook', 'instagram', 'google', 'linkedin'])

    def handle(self, *args, **options):
        product_slug = options['product']
        platform = options['platform']

        try:
            product = Product.objects.get(slug=product_slug)
        except Product.DoesNotExist:
            available = list(Product.objects.values_list('slug', flat=True))
            raise CommandError(f'Product "{product_slug}" not found. Available: {available}')

        self.stdout.write(f'\n--- Setting up {platform} for {product.name} ---\n')

        # Show setup guide
        guide = SETUP_GUIDES.get(platform, '')
        if guide:
            self.stdout.write(self.style.WARNING(guide))

        # Collect credentials
        account_name = input(f'\nDisplay name (e.g. "{product.name} {platform.title()}"): ').strip()
        if not account_name:
            account_name = f'{product.name} {platform.title()}'

        page_id = input('Page/Account ID: ').strip()
        if not page_id:
            raise CommandError('Page/Account ID is required')

        access_token = input('Access Token: ').strip()
        if not access_token:
            raise CommandError('Access Token is required')

        refresh_token = input('Refresh Token (press Enter to skip): ').strip()

        # Check for existing account
        existing = SocialAccount.objects.filter(
            product=product,
            platform=platform,
            page_id=page_id,
        ).first()

        if existing:
            self.stdout.write(self.style.WARNING(
                f'\nExisting account found: {existing.account_name} (id={existing.id})'
            ))
            confirm = input('Update credentials? [y/N]: ').strip().lower()
            if confirm != 'y':
                self.stdout.write('Cancelled.')
                return
            existing.account_name = account_name
            existing.access_token = access_token
            if refresh_token:
                existing.refresh_token = refresh_token
            existing.is_active = True
            existing.save()
            self.stdout.write(self.style.SUCCESS(f'Updated: {existing}'))
        else:
            account = SocialAccount.objects.create(
                product=product,
                platform=platform,
                account_name=account_name,
                page_id=page_id,
                access_token=access_token,
                refresh_token=refresh_token,
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f'Created: {account}'))

        # Verify connectivity
        self.stdout.write('\nVerifying connection...')
        self._verify(platform, page_id, access_token)

    def _verify(self, platform, page_id, access_token):
        """Quick API call to verify the credentials work."""
        import requests

        try:
            if platform == 'facebook':
                resp = requests.get(
                    f'https://graph.facebook.com/v21.0/{page_id}',
                    params={'fields': 'name,id', 'access_token': access_token},
                    timeout=10,
                )
                if resp.status_code == 200:
                    name = resp.json().get('name', 'unknown')
                    self.stdout.write(self.style.SUCCESS(f'Connected to Facebook Page: {name}'))
                else:
                    self.stdout.write(self.style.ERROR(f'Facebook API error: {resp.text[:200]}'))

            elif platform == 'instagram':
                resp = requests.get(
                    f'https://graph.facebook.com/v21.0/{page_id}',
                    params={'fields': 'name,username', 'access_token': access_token},
                    timeout=10,
                )
                if resp.status_code == 200:
                    username = resp.json().get('username', 'unknown')
                    self.stdout.write(self.style.SUCCESS(f'Connected to Instagram: @{username}'))
                else:
                    self.stdout.write(self.style.ERROR(f'Instagram API error: {resp.text[:200]}'))

            elif platform == 'google':
                resp = requests.get(
                    f'https://mybusiness.googleapis.com/v4/{page_id}',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10,
                )
                if resp.status_code == 200:
                    name = resp.json().get('locationName', 'unknown')
                    self.stdout.write(self.style.SUCCESS(f'Connected to Google Business: {name}'))
                else:
                    self.stdout.write(self.style.ERROR(f'Google API error: {resp.text[:200]}'))

            elif platform == 'linkedin':
                resp = requests.get(
                    f'https://api.linkedin.com/v2/organizations/{page_id}',
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'X-Restli-Protocol-Version': '2.0.0',
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    name = resp.json().get('localizedName', 'unknown')
                    self.stdout.write(self.style.SUCCESS(f'Connected to LinkedIn Org: {name}'))
                else:
                    self.stdout.write(self.style.ERROR(f'LinkedIn API error: {resp.text[:200]}'))

        except requests.RequestException as exc:
            self.stdout.write(self.style.ERROR(f'Connection error: {exc}'))
