"""
Sync social post content from a markdown source into SocialPost rows.

Usage:
    python manage.py sync_content --brand taggiq
    python manage.py sync_content --brand taggiq --start-date 2026-04-14
    python manage.py sync_content --brand taggiq --dry-run
    python manage.py sync_content --brand taggiq --markdown /custom/path.md
"""
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from campaigns.models import Product
from social_studio.services.content_sync import sync_posts, DEFAULT_TAGGIQ_MARKDOWN


class Command(BaseCommand):
    help = 'Sync social posts from a markdown content plan into SocialPost rows'

    def add_arguments(self, parser):
        parser.add_argument('--brand', type=str, default='taggiq', help='Product slug')
        parser.add_argument('--markdown', type=str, help='Override markdown source path')
        parser.add_argument('--start-date', type=str, help='Reschedule onto weekdays from YYYY-MM-DD')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        brand = options['brand']
        try:
            product = Product.objects.get(slug=brand)
        except Product.DoesNotExist:
            raise CommandError(f'Product not found: slug={brand}')

        markdown_path = Path(options['markdown']) if options['markdown'] else DEFAULT_TAGGIQ_MARKDOWN
        if not markdown_path.exists():
            raise CommandError(f'Markdown source not found: {markdown_path}')

        start_date = None
        if options['start_date']:
            try:
                start_date = date.fromisoformat(options['start_date'])
            except ValueError:
                raise CommandError(f'Invalid --start-date: {options["start_date"]}')

        self.stdout.write(f'Syncing {brand} from {markdown_path}...')
        summary = sync_posts(
            product,
            markdown_path=markdown_path,
            start_date=start_date,
            dry_run=options['dry_run'],
        )

        prefix = '[DRY RUN] ' if summary['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Parsed {summary["parsed"]} post(s). '
            f'Created {summary["created"]}, updated {summary["updated"]}.'
        ))
        if summary['schedule_start']:
            self.stdout.write(
                f'Schedule: {summary["schedule_start"]} to {summary["schedule_end"]}'
            )
