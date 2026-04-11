"""
Content sync: parse a LINKEDIN_POSTS.md markdown file into SocialPost rows.

The markdown format follows the convention in taggiqpos/marketing/social/.
Each post starts with `### Post N` followed by metadata lines and a body.

KISS: just parse and upsert. No content-source registry, no sync history
model, no webhooks. When a second source shows up (google doc, notion),
we'll factor out a ContentSource model — not before.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable


# Default taggiq markdown source; override per sync call or via
# TAGGIQ_MARKDOWN_PATH env var (set by docker-compose bind-mount).
DEFAULT_TAGGIQ_MARKDOWN = Path(
    os.getenv(
        'TAGGIQ_MARKDOWN_PATH',
        '/Users/pinani/Documents/taggiqpos/marketing/social/LINKEDIN_POSTS.md',
    )
)


def parse_posts(filepath: Path | str) -> list[dict]:
    """Parse a LINKEDIN_POSTS.md file into structured post dicts.

    Returns a list of dicts with keys: post_number, pillar, content,
    hashtags, link_url.
    """
    with open(filepath) as f:
        content = f.read()

    post_blocks = re.split(r'### Post (\d+)', content)[1:]
    posts: list[dict] = []

    for i in range(0, len(post_blocks), 2):
        num = int(post_blocks[i])
        block = post_blocks[i + 1]

        header_match = re.match(r'\s*-\s*(.*?)\s*-\s*Week \d+,\s*\w+', block)
        pillar = header_match.group(1).strip() if header_match else ''

        hashtags_match = re.search(r'\*\*Hashtags:\*\*\s*(.*)', block)
        hashtags = hashtags_match.group(1).strip() if hashtags_match else ''

        body_end = block.find('**Media:**')
        if body_end == -1:
            body_end = block.find('**Hashtags:**')

        header_end = block.find('\n\n')
        if header_end == -1:
            header_end = 0

        body = block[header_end:body_end].strip() if body_end > 0 else block[header_end:].strip()

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


def weekday_schedule(start: date, count: int) -> list[date]:
    """Generate `count` consecutive weekday dates starting from `start`."""
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def sync_posts(
    product,
    *,
    markdown_path: Path | str = DEFAULT_TAGGIQ_MARKDOWN,
    start_date: date | None = None,
    dry_run: bool = False,
) -> dict:
    """Parse the markdown file and upsert `SocialPost` rows for the product.

    - If `start_date` is provided, re-schedules all posts onto weekdays from
      that date. Otherwise leaves existing scheduled_date values untouched.
    - Content / pillar / hashtags / link_url are always refreshed from the
      markdown (source of truth).
    - Returns a summary dict: {parsed, created, updated, dry_run}.
    """
    # Deferred import so this module can be imported without Django setup
    from social_studio.models import SocialPost

    posts_data = parse_posts(markdown_path)
    dates = weekday_schedule(start_date, len(posts_data)) if start_date else None

    created = 0
    updated = 0

    for idx, post_data in enumerate(posts_data):
        defaults = {
            'content': post_data['content'],
            'hashtags': post_data['hashtags'],
            'link_url': post_data['link_url'],
            'pillar': post_data['pillar'],
        }
        if dates is not None:
            defaults['scheduled_date'] = dates[idx]

        if dry_run:
            continue

        _, was_created = SocialPost.objects.update_or_create(
            product=product,
            post_number=post_data['post_number'],
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {
        'parsed': len(posts_data),
        'created': created,
        'updated': updated,
        'dry_run': dry_run,
        'schedule_start': dates[0] if dates else None,
        'schedule_end': dates[-1] if dates else None,
    }
