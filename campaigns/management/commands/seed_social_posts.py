"""
Seed social posts from the TaggIQ LinkedIn content plan.

Usage:
    python manage.py seed_social_posts --start-date 2026-04-14
    python manage.py seed_social_posts --start-date 2026-04-14 --dry-run

Reads LINKEDIN_POSTS.md, parses 30 posts, creates SocialPost records
scheduled on weekdays starting from the given date.
"""
import re
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from campaigns.models import Product, SocialPost


POSTS_FILE = '/Users/pinani/Documents/taggiqpos/marketing/social/LINKEDIN_POSTS.md'


def parse_posts(filepath):
    """Parse LINKEDIN_POSTS.md into structured post dicts."""
    with open(filepath) as f:
        content = f.read()

    post_blocks = re.split(r'### Post (\d+)', content)[1:]
    posts = []

    for i in range(0, len(post_blocks), 2):
        num = int(post_blocks[i])
        block = post_blocks[i + 1]

        header_match = re.match(r'\s*-\s*(.*?)\s*-\s*Week \d+,\s*\w+', block)
        pillar = header_match.group(1).strip() if header_match else ''

        hashtags_match = re.search(r'\*\*Hashtags:\*\*\s*(.*)', block)
        hashtags = hashtags_match.group(1).strip() if hashtags_match else ''

        cta_match = re.search(r'\*\*CTA:\*\*\s*(.*)', block)

        body_end = block.find('**Media:**')
        if body_end == -1:
            body_end = block.find('**Hashtags:**')

        header_end = block.find('\n\n')
        if header_end == -1:
            header_end = 0

        body = block[header_end:body_end].strip() if body_end > 0 else block[header_end:].strip()
        body = body.strip()

        link_url = ''
        if 'taggiq.com' in body.lower():
            link_match = re.search(r'(https?://\S*taggiq\.com\S*)', body)
            if link_match:
                link_url = link_match.group(1).rstrip('.')

        posts.append({
            'post_number': num,
            'pillar': pillar,
            'content': body,
            'hashtags': hashtags,
            'link_url': link_url,
        })

    return posts


def weekday_schedule(start_date, count):
    """Generate `count` weekday dates starting from start_date."""
    dates = []
    current = start_date
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


class Command(BaseCommand):
    help = 'Seed social posts from TaggIQ LinkedIn content plan'

    def add_arguments(self, parser):
        parser.add_argument('--start-date', type=str, required=True, help='Start date YYYY-MM-DD')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        start = date.fromisoformat(options['start_date'])
        product = Product.objects.get(slug='taggiq')

        self.stdout.write(f'Parsing {POSTS_FILE}...')
        posts = parse_posts(POSTS_FILE)
        self.stdout.write(f'Found {len(posts)} posts')

        dates = weekday_schedule(start, len(posts))

        created = 0
        for post_data, sched_date in zip(posts, dates):
            if options['dry_run']:
                self.stdout.write(
                    f'  #{post_data["post_number"]:2d} | {sched_date} | {post_data["pillar"]:<25} '
                    f'| {post_data["content"][:60]}...'
                )
                continue

            _, was_created = SocialPost.objects.update_or_create(
                product=product,
                post_number=post_data['post_number'],
                defaults={
                    'content': post_data['content'],
                    'hashtags': post_data['hashtags'],
                    'link_url': post_data.get('link_url', ''),
                    'pillar': post_data['pillar'],
                    'scheduled_date': sched_date,
                },
            )
            if was_created:
                created += 1

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'\n[DRY RUN] Would create {len(posts)} posts'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nSeeded {len(posts)} posts ({created} new). '
                f'Schedule: {dates[0]} to {dates[-1]}'
            ))
