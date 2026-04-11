"""
Interactive setup for LinkedIn company page posting.

Usage:
    python manage.py setup_linkedin

Walks through:
  1. Getting your Organization ID from LinkedIn
  2. Creating a LinkedIn App
  3. OAuth token exchange
  4. Creating the SocialAccount record
  5. Test post (dry run)
"""
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests
from django.core.management.base import BaseCommand

from campaigns.models import Product
from social_studio.models import SocialAccount


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Captures the OAuth callback code."""
    code = None

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        OAuthCallbackHandler.code = query.get('code', [None])[0]
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<h2>Done! You can close this tab and go back to the terminal.</h2>')

    def log_message(self, format, *args):
        pass


class Command(BaseCommand):
    help = 'Interactive LinkedIn company page setup'

    def handle(self, *args, **options):
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('  LinkedIn Company Page Setup')
        self.stdout.write('=' * 60)

        # Step 1: Org ID
        self.stdout.write('\n--- Step 1: Get your Organization ID ---\n')
        self.stdout.write('Go to your LinkedIn company page admin:')
        self.stdout.write('  https://www.linkedin.com/company/taggiq/admin/')
        self.stdout.write('')
        self.stdout.write('The URL contains your org ID. For example:')
        self.stdout.write('  linkedin.com/company/12345678/ -> org ID is 12345678')
        self.stdout.write('')
        self.stdout.write('Or go to: https://www.linkedin.com/company/taggiq/')
        self.stdout.write('Click "Admin tools" -> the URL will show the numeric ID.')
        self.stdout.write('')
        org_id = input('Enter your LinkedIn Organization ID (numeric): ').strip()
        if not org_id.isdigit():
            self.stdout.write(self.style.ERROR('Organization ID must be numeric'))
            return

        # Step 2: App credentials
        self.stdout.write('\n--- Step 2: LinkedIn App ---\n')
        self.stdout.write('If you don\'t have a LinkedIn App yet:')
        self.stdout.write('  1. Go to https://www.linkedin.com/developers/apps')
        self.stdout.write('  2. Click "Create app"')
        self.stdout.write('  3. Fill in:')
        self.stdout.write('     - App name: "TaggIQ Social"')
        self.stdout.write('     - LinkedIn Page: select TaggIQ')
        self.stdout.write('     - Logo: upload TaggIQ logo')
        self.stdout.write('  4. After creation, go to "Products" tab')
        self.stdout.write('     - Request "Share on LinkedIn" (instant approval)')
        self.stdout.write('     - Request "Community Management API" if available')
        self.stdout.write('  5. Go to "Auth" tab to find Client ID and Client Secret')
        self.stdout.write('  6. Add redirect URL: http://localhost:9876/callback')
        self.stdout.write('')

        client_id = input('Enter Client ID: ').strip()
        client_secret = input('Enter Client Secret: ').strip()

        if not client_id or not client_secret:
            self.stdout.write(self.style.ERROR('Both Client ID and Secret required'))
            return

        # Step 3: OAuth flow
        self.stdout.write('\n--- Step 3: Authorize ---\n')
        self.stdout.write('Opening browser for LinkedIn authorization...')

        redirect_uri = 'http://localhost:9876/callback'
        scopes = 'w_member_social%20w_organization_social%20r_organization_social'
        auth_url = (
            f'https://www.linkedin.com/oauth/v2/authorization'
            f'?response_type=code'
            f'&client_id={client_id}'
            f'&redirect_uri={redirect_uri}'
            f'&scope={scopes}'
        )

        self.stdout.write(f'\nIf browser doesn\'t open, go to:\n{auth_url}\n')
        webbrowser.open(auth_url)

        self.stdout.write('Waiting for authorization callback...')
        server = HTTPServer(('localhost', 9876), OAuthCallbackHandler)
        server.handle_request()
        server.server_close()

        code = OAuthCallbackHandler.code
        if not code:
            self.stdout.write(self.style.ERROR('No authorization code received'))
            return

        self.stdout.write(self.style.SUCCESS('Authorization code received!'))

        # Step 4: Exchange code for token
        self.stdout.write('\nExchanging for access token...')
        resp = requests.post('https://www.linkedin.com/oauth/v2/accessToken', data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'client_secret': client_secret,
        }, timeout=30)

        if resp.status_code != 200:
            self.stdout.write(self.style.ERROR(f'Token exchange failed: {resp.text}'))
            return

        token_data = resp.json()
        access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 5184000)
        refresh_token = token_data.get('refresh_token', '')

        self.stdout.write(self.style.SUCCESS(f'Access token received! Expires in {expires_in // 86400} days'))

        # Step 5: Verify by fetching org info
        self.stdout.write('\nVerifying organization access...')
        verify_resp = requests.get(
            f'https://api.linkedin.com/v2/organizations/{org_id}',
            headers={
                'Authorization': f'Bearer {access_token}',
                'X-Restli-Protocol-Version': '2.0.0',
            },
            timeout=15,
        )

        if verify_resp.status_code == 200:
            org_data = verify_resp.json()
            org_name = org_data.get('localizedName', 'Unknown')
            self.stdout.write(self.style.SUCCESS(f'Verified: {org_name} (ID: {org_id})'))
        else:
            self.stdout.write(self.style.WARNING(
                f'Could not verify org (HTTP {verify_resp.status_code}). '
                f'Token may still work for posting. Continuing...'
            ))

        # Step 6: Save to database
        self.stdout.write('\nSaving to database...')
        product = Product.objects.get(slug='taggiq')

        from django.utils import timezone
        from datetime import timedelta

        account, created = SocialAccount.objects.update_or_create(
            product=product,
            platform='linkedin',
            defaults={
                'account_name': f'TaggIQ LinkedIn Page',
                'page_id': org_id,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_expires_at': timezone.now() + timedelta(seconds=expires_in),
                'is_active': True,
            },
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} SocialAccount: {account}'))

        # Step 7: Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('  SETUP COMPLETE')
        self.stdout.write('=' * 60)
        self.stdout.write(f'\n  Organization: {org_id}')
        self.stdout.write(f'  Token expires: {account.token_expires_at:%Y-%m-%d}')
        self.stdout.write(f'  Refresh token: {"Yes" if refresh_token else "No"}')
        self.stdout.write(f'\n  Test with:')
        self.stdout.write(f'    python manage.py post_to_social --dry-run --post-number 1')
        self.stdout.write(f'\n  First automated post: Monday 2026-04-14 at 9am')

        # Save client credentials to .env hint
        self.stdout.write(f'\n  IMPORTANT: Save these in your .env for token refresh:')
        self.stdout.write(f'    LINKEDIN_CLIENT_ID={client_id}')
        self.stdout.write(f'    LINKEDIN_CLIENT_SECRET={client_secret}')
        self.stdout.write('')
