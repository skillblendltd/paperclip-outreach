"""
One-time migration: update all TaggIQ campaign from_email addresses
from @mail.taggiq.com to @mail.taggiqpos.com.

Run once on EC2 after DNS verification is confirmed:

    python manage.py migrate_taggiq_sending_domain
    python manage.py migrate_taggiq_sending_domain --dry-run
    python manage.py migrate_taggiq_sending_domain --reverse  # roll back if needed
"""
from django.core.management.base import BaseCommand

from campaigns.models import Campaign

OLD_DOMAIN = 'mail.taggiq.com'
NEW_DOMAIN = 'mail.taggiqpos.com'


class Command(BaseCommand):
    help = 'Migrate TaggIQ campaign from_email from mail.taggiq.com to mail.taggiqpos.com'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
        parser.add_argument('--reverse', action='store_true', help='Roll back: new -> old domain')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reverse = options['reverse']

        src = NEW_DOMAIN if reverse else OLD_DOMAIN
        dst = OLD_DOMAIN if reverse else NEW_DOMAIN

        campaigns = Campaign.objects.filter(from_email__icontains=src)
        campaign_list = list(campaigns.order_by('name'))
        if not campaign_list:
            self.stdout.write(f'No campaigns with @{src} found.')
            return

        self.stdout.write(f'{"DRY RUN - " if dry_run else ""}Migrating @{src} -> @{dst}:')
        count = 0
        for c in campaign_list:
            new_email = c.from_email.replace(src, dst)
            self.stdout.write(f'  [{c.id}] {c.name}')
            self.stdout.write(f'      {c.from_email} -> {new_email}')
            if not dry_run:
                c.from_email = new_email
                c.save(update_fields=['from_email'])
                count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDry run complete - {len(campaign_list)} campaigns would be updated.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nDone - {count} campaigns updated.'))
