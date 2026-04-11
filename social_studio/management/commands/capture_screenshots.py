"""
Capture TaggIQ product screenshots via Playwright.

Run on demand when the TaggIQ UI changes. Outputs PNGs to
social_studio/static/taggiq-ui/<slug>.png which bespoke HTML can reference.

Usage:
    python manage.py capture_screenshots
    python manage.py capture_screenshots --base-url http://localhost:5180
"""
import os

from django.core.management.base import BaseCommand

from social_studio.services.screenshots import capture_routes, TAGGIQ_FRONTEND_URL


class Command(BaseCommand):
    help = 'Capture TaggIQ product screenshots for social post assets'

    def add_arguments(self, parser):
        parser.add_argument('--base-url', type=str, default=TAGGIQ_FRONTEND_URL)
        parser.add_argument('--session-cookie', type=str, help='Optional sessionid cookie value')

    def handle(self, *args, **options):
        base_url = options['base_url']
        self.stdout.write(f'Capturing TaggIQ UI from {base_url}')

        summary = capture_routes(
            base_url=base_url,
            session_cookie=options.get('session_cookie') or os.getenv('TAGGIQ_SESSION_COOKIE', ''),
        )

        for slug in summary['captured']:
            self.stdout.write(self.style.SUCCESS(f'  ✓ {slug}.png'))
        for slug, err in summary['failed']:
            self.stdout.write(self.style.ERROR(f'  ✗ {slug}: {err}'))

        self.stdout.write(f'\nOutput: {summary["out_dir"]}')
        self.stdout.write(f'Captured {len(summary["captured"])}, failed {len(summary["failed"])}')
