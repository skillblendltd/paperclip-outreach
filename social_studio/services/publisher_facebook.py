"""
Facebook Pages publisher - post text + optional image to a Facebook Page.

Uses the Facebook Graph API v21.0:
    - Text + link: POST /{page_id}/feed
    - Image + text: POST /{page_id}/photos

Auth: Page Access Token stored in SocialAccount.access_token.
The page_id field on SocialAccount is the Facebook Page ID.

See: https://developers.facebook.com/docs/pages-api/posts
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

GRAPH_API = 'https://graph.facebook.com/v21.0'


def publish_post(account, post) -> Tuple[Optional[str], Optional[str]]:
    """Publish a SocialPost to a Facebook Page.

    Returns (platform_post_id, error_message). Exactly one will be None.
    """
    access_token = account.access_token
    page_id = account.page_id

    if not access_token or not page_id:
        return None, 'Missing access_token or page_id on SocialAccount'

    body = post.content
    if post.hashtags:
        body += f'\n\n{post.hashtags}'

    image_path = _resolve_image_path(post)

    try:
        if image_path and image_path.exists():
            post_id = _post_with_image(access_token, page_id, body, image_path)
        else:
            post_id = _post_text(access_token, page_id, body, post.link_url)
    except FacebookPublishError as exc:
        return None, str(exc)

    return post_id, None


class FacebookPublishError(Exception):
    pass


def _resolve_image_path(post) -> Optional[Path]:
    if not post.media_path:
        return None
    base = Path(settings.BASE_DIR) / 'social_studio'
    return (base / post.media_path).resolve()


def _post_text(access_token: str, page_id: str, message: str, link_url: str = '') -> str:
    """Post text (optionally with link) to the page feed."""
    payload = {
        'message': message,
        'access_token': access_token,
    }
    if link_url:
        payload['link'] = link_url

    resp = requests.post(
        f'{GRAPH_API}/{page_id}/feed',
        data=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise FacebookPublishError(
            f'feed POST HTTP {resp.status_code}: {resp.text[:500]}'
        )

    post_id = resp.json().get('id', '')
    if not post_id:
        raise FacebookPublishError(f'feed POST returned no id: {resp.json()}')
    return post_id


def _post_with_image(access_token: str, page_id: str, message: str, image_path: Path) -> str:
    """Post image + caption to the page photos endpoint."""
    with open(image_path, 'rb') as fh:
        resp = requests.post(
            f'{GRAPH_API}/{page_id}/photos',
            data={
                'message': message,
                'access_token': access_token,
            },
            files={
                'source': (image_path.name, fh, 'image/png'),
            },
            timeout=60,
        )

    if resp.status_code not in (200, 201):
        raise FacebookPublishError(
            f'photos POST HTTP {resp.status_code}: {resp.text[:500]}'
        )

    post_id = resp.json().get('post_id') or resp.json().get('id', '')
    if not post_id:
        raise FacebookPublishError(f'photos POST returned no id: {resp.json()}')
    return post_id
