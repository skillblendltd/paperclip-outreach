"""
Publish SocialPost(s) to their configured SocialAccounts.

Usage:
    python manage.py publish_post --next-scheduled     # cron-friendly (pick today's)
    python manage.py publish_post --post-number 1
    python manage.py publish_post --next-scheduled --dry-run
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from social_studio.models import SocialPost, SocialAccount, SocialPostDelivery
from social_studio.services import publisher_linkedin


PUBLISHERS = {
    'linkedin': publisher_linkedin.publish_post,
}


class Command(BaseCommand):
    help = 'Publish scheduled SocialPosts to LinkedIn (and other platforms in v2)'

    def add_arguments(self, parser):
        parser.add_argument('--next-scheduled', action='store_true', help='Publish posts scheduled for today')
        parser.add_argument('--post-number', type=int)
        parser.add_argument('--product', type=str, default='taggiq')
        parser.add_argument('--platform', type=str, help='Filter to one platform (e.g. linkedin)')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        posts = self._select_posts(options)
        if not posts:
            self.stdout.write('No posts to publish.')
            return

        self.stdout.write(f'Publishing {posts.count()} post(s)')

        for post in posts:
            self._publish_one(post, options)

    def _select_posts(self, options):
        qs = SocialPost.objects.all()
        if options['post_number']:
            return qs.filter(post_number=options['post_number'])
        if options['next_scheduled']:
            return qs.filter(
                scheduled_date=date.today(),
                product__slug=options['product'],
            )
        raise CommandError('Specify --next-scheduled or --post-number')

    def _publish_one(self, post, options):
        self.stdout.write(f'\n=== Post #{post.post_number} [{post.pillar}] ===')
        preview = post.content[:200] + '...' if len(post.content) > 200 else post.content
        self.stdout.write(preview)
        if post.media_path:
            self.stdout.write(f'media: {post.media_path}')
        else:
            self.stdout.write(self.style.WARNING('media: (none — will post text-only)'))

        accounts = SocialAccount.objects.filter(
            product=post.product,
            is_active=True,
        )
        if options['platform']:
            accounts = accounts.filter(platform=options['platform'])

        if not accounts.exists():
            self.stdout.write(self.style.WARNING(
                f'  No active SocialAccount for {post.product}. Run setup_linkedin first.'
            ))
            return

        for account in accounts:
            delivery, _ = SocialPostDelivery.objects.get_or_create(
                post=post,
                account=account,
                defaults={'status': 'pending'},
            )
            if delivery.status == 'published':
                self.stdout.write(f'  {account.platform}: already published')
                continue

            if options['dry_run']:
                self.stdout.write(self.style.SUCCESS(
                    f'  {account.platform}: [DRY RUN] would publish to {account.account_name}'
                ))
                continue

            publisher = PUBLISHERS.get(account.platform)
            if not publisher:
                self.stdout.write(self.style.WARNING(
                    f'  {account.platform}: not implemented in v1'
                ))
                delivery.status = 'skipped'
                delivery.error = 'Publisher not implemented in v1'
                delivery.save()
                continue

            try:
                post_urn, error = publisher(account, post)
                if post_urn:
                    delivery.status = 'published'
                    delivery.platform_post_id = post_urn
                    delivery.published_at = timezone.now()
                    delivery.error = ''
                    delivery.save()
                    self.stdout.write(self.style.SUCCESS(
                        f'  {account.platform}: published ({post_urn})'
                    ))
                else:
                    delivery.status = 'failed'
                    delivery.error = error or 'unknown'
                    delivery.save()
                    self.stdout.write(self.style.ERROR(f'  {account.platform}: {error}'))
            except Exception as exc:
                delivery.status = 'failed'
                delivery.error = str(exc)[:500]
                delivery.save()
                self.stdout.write(self.style.ERROR(f'  {account.platform}: exception: {exc}'))
