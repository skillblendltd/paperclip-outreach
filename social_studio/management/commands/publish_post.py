"""
Publish SocialPost(s) to their configured SocialAccounts.

Supports all platforms: LinkedIn, Facebook, Instagram, Google Business.
Each platform has its own publisher in social_studio/services/.

Usage:
    python manage.py publish_post --next-scheduled                    # all products, today's posts
    python manage.py publish_post --next-scheduled --product taggiq   # one product
    python manage.py publish_post --post-number 1 --product taggiq    # specific post
    python manage.py publish_post --next-scheduled --platform facebook --dry-run
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from social_studio.models import SocialPost, SocialAccount, SocialPostDelivery
from social_studio.services import (
    publisher_linkedin,
    publisher_facebook,
    publisher_instagram,
    publisher_google,
)


PUBLISHERS = {
    'linkedin': publisher_linkedin.publish_post,
    'facebook': publisher_facebook.publish_post,
    'instagram': publisher_instagram.publish_post,
    'google': publisher_google.publish_post,
}


class Command(BaseCommand):
    help = 'Publish scheduled SocialPosts to configured platforms (LinkedIn, Facebook, Instagram, Google)'

    def add_arguments(self, parser):
        parser.add_argument('--next-scheduled', action='store_true', help='Publish posts scheduled for today')
        parser.add_argument('--post-number', type=int)
        parser.add_argument('--product', type=str, default='', help='Filter by product slug (empty = all products)')
        parser.add_argument('--platform', type=str, help='Filter to one platform (e.g. facebook)')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        posts = self._select_posts(options)
        if not posts:
            self.stdout.write('No posts to publish.')
            return

        self.stdout.write(f'Publishing {posts.count()} post(s)')

        published = 0
        failed = 0
        skipped = 0
        for post in posts:
            p, f, s = self._publish_one(post, options)
            published += p
            failed += f
            skipped += s

        self.stdout.write(
            f'\nDone: {published} published, {failed} failed, {skipped} skipped'
        )

    def _select_posts(self, options):
        qs = SocialPost.objects.all()

        if options['product']:
            qs = qs.filter(product__slug=options['product'])

        if options['post_number']:
            return qs.filter(post_number=options['post_number'])
        if options['next_scheduled']:
            return qs.filter(scheduled_date=date.today())

        raise CommandError('Specify --next-scheduled or --post-number')

    def _publish_one(self, post, options):
        product_name = post.product.name if post.product else 'unknown'
        self.stdout.write(f'\n=== [{product_name}] Post #{post.post_number} ===')
        preview = post.content[:200] + '...' if len(post.content) > 200 else post.content
        self.stdout.write(preview)
        if post.media_path:
            self.stdout.write(f'media: {post.media_path}')

        accounts = SocialAccount.objects.filter(
            product=post.product,
            is_active=True,
        )
        if options['platform']:
            accounts = accounts.filter(platform=options['platform'])

        if not accounts.exists():
            self.stdout.write(self.style.WARNING(
                f'  No active SocialAccount for {product_name}.'
            ))
            return 0, 0, 0

        published = 0
        failed = 0
        skipped = 0

        for account in accounts:
            delivery, _ = SocialPostDelivery.objects.get_or_create(
                post=post,
                account=account,
                defaults={'status': 'pending'},
            )
            if delivery.status == 'published':
                self.stdout.write(f'  {account.platform}: already published')
                skipped += 1
                continue

            if options['dry_run']:
                self.stdout.write(self.style.SUCCESS(
                    f'  {account.platform}: [DRY RUN] would publish to {account.account_name}'
                ))
                skipped += 1
                continue

            publisher = PUBLISHERS.get(account.platform)
            if not publisher:
                self.stdout.write(self.style.WARNING(
                    f'  {account.platform}: no publisher available'
                ))
                delivery.status = 'skipped'
                delivery.error = f'No publisher for platform: {account.platform}'
                delivery.save()
                skipped += 1
                continue

            try:
                post_id, error = publisher(account, post)
                if post_id:
                    delivery.status = 'published'
                    delivery.platform_post_id = post_id
                    delivery.published_at = timezone.now()
                    delivery.error = ''
                    delivery.save()
                    self.stdout.write(self.style.SUCCESS(
                        f'  {account.platform}: published ({post_id})'
                    ))
                    published += 1
                else:
                    delivery.status = 'failed'
                    delivery.error = error or 'unknown'
                    delivery.save()
                    self.stdout.write(self.style.ERROR(f'  {account.platform}: {error}'))
                    failed += 1
            except Exception as exc:
                delivery.status = 'failed'
                delivery.error = str(exc)[:500]
                delivery.save()
                self.stdout.write(self.style.ERROR(f'  {account.platform}: exception: {exc}'))
                failed += 1

        return published, failed, skipped
