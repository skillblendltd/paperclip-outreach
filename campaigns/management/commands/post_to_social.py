"""
Post scheduled content to social media platforms.

Publishes today's scheduled SocialPost to all active SocialAccounts for
the post's product. Each platform has its own publisher function.

Usage:
    python manage.py post_to_social                    # Post today's content
    python manage.py post_to_social --dry-run          # Preview without posting
    python manage.py post_to_social --status           # Show schedule overview
    python manage.py post_to_social --post-number 5    # Force-post a specific post
    python manage.py post_to_social --product taggiq   # Filter by product
    python manage.py post_to_social --platform linkedin # One platform only

Cron: 0 9 * * 1-5 (weekdays at 9am)
"""
import logging
from datetime import date

import requests
from django.conf import settings
from django.utils import timezone
from django.core.management.base import BaseCommand

from social_studio.models import SocialAccount, SocialPost, SocialPostDelivery

logger = logging.getLogger(__name__)


def publish_linkedin(account, post):
    """Publish a post to a LinkedIn company page. Returns (post_id, error)."""
    access_token = account.access_token or getattr(settings, 'LINKEDIN_ACCESS_TOKEN', '')
    org_id = account.page_id or getattr(settings, 'LINKEDIN_ORGANIZATION_ID', '')

    if not access_token or not org_id:
        return None, 'Missing access_token or page_id'

    body = post.content
    if post.hashtags:
        body += f'\n\n{post.hashtags}'

    payload = {
        'author': f'urn:li:organization:{org_id}',
        'lifecycleState': 'PUBLISHED',
        'specificContent': {
            'com.linkedin.ugc.ShareContent': {
                'shareCommentary': {'text': body},
                'shareMediaCategory': 'NONE',
            },
        },
        'visibility': {
            'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC',
        },
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
    }

    resp = requests.post(
        'https://api.linkedin.com/v2/ugcPosts',
        json=payload,
        headers=headers,
        timeout=30,
    )

    if resp.status_code in (200, 201):
        post_id = resp.json().get('id', '')
        if post.link_url:
            _linkedin_first_comment(post_id, post.link_url, org_id, headers)
        return post_id, None
    else:
        return None, f'HTTP {resp.status_code}: {resp.text[:500]}'


def _linkedin_first_comment(post_urn, text, org_id, headers):
    try:
        requests.post(
            f'https://api.linkedin.com/v2/socialActions/{post_urn}/comments',
            json={
                'actor': f'urn:li:organization:{org_id}',
                'message': {'text': text},
            },
            headers=headers,
            timeout=15,
        )
    except requests.RequestException:
        pass


def publish_facebook(account, post):
    """Publish to Facebook page. Returns (post_id, error)."""
    return None, 'Facebook publisher not yet implemented'


def publish_twitter(account, post):
    """Publish to Twitter/X. Returns (post_id, error)."""
    return None, 'Twitter publisher not yet implemented'


def publish_instagram(account, post):
    """Publish to Instagram. Returns (post_id, error)."""
    return None, 'Instagram publisher not yet implemented'


def publish_google(account, post):
    """Publish to Google Business. Returns (post_id, error)."""
    return None, 'Google Business publisher not yet implemented'


PUBLISHERS = {
    'linkedin': publish_linkedin,
    'facebook': publish_facebook,
    'twitter': publish_twitter,
    'instagram': publish_instagram,
    'google': publish_google,
}


class Command(BaseCommand):
    help = 'Post scheduled content to social media platforms'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--status', action='store_true')
        parser.add_argument('--post-number', type=int)
        parser.add_argument('--product', type=str, help='Product slug filter')
        parser.add_argument('--platform', type=str, help='Platform filter (linkedin, facebook, etc.)')

    def handle(self, *args, **options):
        if options['status']:
            return self._show_status(options)

        posts = SocialPost.objects.filter(scheduled_date=date.today())
        if options['post_number']:
            posts = SocialPost.objects.filter(post_number=options['post_number'])
        if options['product']:
            posts = posts.filter(product__slug=options['product'])

        if not posts.exists():
            self.stdout.write(f'No posts scheduled for {date.today()}')
            return

        for post in posts:
            accounts = SocialAccount.objects.filter(
                product=post.product,
                is_active=True,
            )
            if options['platform']:
                accounts = accounts.filter(platform=options['platform'])

            if not accounts.exists():
                self.stdout.write(f'  No active accounts for {post.product}')
                continue

            self.stdout.write(f'\n{"=" * 60}')
            self.stdout.write(f'Post #{post.post_number} - {post.pillar} [{post.product}]')
            self.stdout.write(f'{"=" * 60}')
            preview = post.content[:300] + '...' if len(post.content) > 300 else post.content
            self.stdout.write(f'\n{preview}\n')

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
                        f'  {account.platform}: no publisher available'
                    ))
                    continue

                try:
                    post_id, error = publisher(account, post)
                    if error:
                        delivery.status = 'failed'
                        delivery.error = error
                        delivery.save(update_fields=['status', 'error', 'updated_at'])
                        self.stdout.write(self.style.ERROR(f'  {account.platform}: FAILED - {error}'))
                    else:
                        delivery.status = 'published'
                        delivery.platform_post_id = post_id or ''
                        delivery.published_at = timezone.now()
                        delivery.save(update_fields=['status', 'platform_post_id', 'published_at', 'updated_at'])
                        self.stdout.write(self.style.SUCCESS(f'  {account.platform}: Published! ID={post_id}'))
                except Exception as e:
                    delivery.status = 'failed'
                    delivery.error = str(e)
                    delivery.save(update_fields=['status', 'error', 'updated_at'])
                    self.stdout.write(self.style.ERROR(f'  {account.platform}: ERROR - {e}'))
                    logger.error(f'Social post failed: {account.platform} #{post.post_number}: {e}')

    def _show_status(self, options):
        posts = SocialPost.objects.all()
        if options.get('product'):
            posts = posts.filter(product__slug=options['product'])

        if not posts.exists():
            self.stdout.write('No social posts in database. Seed them first.')
            return

        self.stdout.write(f'\n{"=" * 80}')
        self.stdout.write(f'Social Post Schedule')
        self.stdout.write(f'{"=" * 80}')

        for p in posts.order_by('scheduled_date', 'post_number'):
            deliveries = p.deliveries.all()
            if deliveries:
                platforms = ' | '.join(f'{d.account.platform}:{d.status}' for d in deliveries)
            else:
                platforms = 'no deliveries'

            sched = str(p.scheduled_date) if p.scheduled_date else 'unset'
            marker = ' <-- TODAY' if p.scheduled_date == date.today() else ''
            self.stdout.write(
                f'  #{p.post_number:2d} | {sched:>10} '
                f'| {p.pillar:<22} | {platforms}{marker}'
            )

        accounts = SocialAccount.objects.filter(is_active=True)
        self.stdout.write(f'\nActive accounts:')
        for a in accounts:
            self.stdout.write(f'  {a.product} -> {a.platform}: {a.account_name}')
