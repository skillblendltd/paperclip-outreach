"""
Instagram Content Publishing API publisher.

Two-step flow:
    1. POST /{ig_user_id}/media  - create a media container
    2. POST /{ig_user_id}/media_publish  - publish it

Auth: Uses the same Facebook Page Access Token (with instagram_content_publish
permission). The page_id on SocialAccount is the Instagram Business Account ID
(NOT the Facebook Page ID - get it via /{fb_page_id}?fields=instagram_business_account).

Image requirement: Instagram requires a publicly accessible image URL for the
container creation step. For local images, we upload to a temporary hosting
endpoint first. In v1, we require media_url on the post (a public URL) or
skip if only local media_path is available.

See: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import requests


logger = logging.getLogger(__name__)

GRAPH_API = 'https://graph.facebook.com/v21.0'

# Instagram container creation is async. Poll for status.
MAX_POLL_ATTEMPTS = 10
POLL_INTERVAL_SECONDS = 3


def publish_post(account, post) -> Tuple[Optional[str], Optional[str]]:
    """Publish a SocialPost to Instagram.

    Returns (platform_post_id, error_message). Exactly one will be None.
    """
    access_token = account.access_token
    ig_user_id = account.page_id  # Instagram Business Account ID

    if not access_token or not ig_user_id:
        return None, 'Missing access_token or page_id (IG Business Account ID) on SocialAccount'

    body = post.content
    if post.hashtags:
        body += f'\n\n{post.hashtags}'

    # Instagram requires a public image URL for media posts
    image_url = post.media_url if post.media_url else ''

    try:
        if image_url:
            post_id = _publish_image_post(access_token, ig_user_id, body, image_url)
        else:
            # Text-only posts are not supported on Instagram.
            # We can do a carousel or single image only.
            return None, 'Instagram requires an image. Set media_url on the post.'
    except InstagramPublishError as exc:
        return None, str(exc)

    return post_id, None


class InstagramPublishError(Exception):
    pass


def _publish_image_post(access_token: str, ig_user_id: str, caption: str, image_url: str) -> str:
    """Two-step publish: create container, then publish."""
    # Step 1: Create media container
    container_resp = requests.post(
        f'{GRAPH_API}/{ig_user_id}/media',
        data={
            'image_url': image_url,
            'caption': caption,
            'access_token': access_token,
        },
        timeout=30,
    )
    if container_resp.status_code not in (200, 201):
        raise InstagramPublishError(
            f'media container POST HTTP {container_resp.status_code}: {container_resp.text[:500]}'
        )

    container_id = container_resp.json().get('id')
    if not container_id:
        raise InstagramPublishError(f'media container returned no id: {container_resp.json()}')

    # Step 2: Wait for container to be ready, then publish
    _wait_for_container(access_token, container_id)

    publish_resp = requests.post(
        f'{GRAPH_API}/{ig_user_id}/media_publish',
        data={
            'creation_id': container_id,
            'access_token': access_token,
        },
        timeout=30,
    )
    if publish_resp.status_code not in (200, 201):
        raise InstagramPublishError(
            f'media_publish POST HTTP {publish_resp.status_code}: {publish_resp.text[:500]}'
        )

    post_id = publish_resp.json().get('id')
    if not post_id:
        raise InstagramPublishError(f'media_publish returned no id: {publish_resp.json()}')
    return post_id


def _wait_for_container(access_token: str, container_id: str) -> None:
    """Poll container status until FINISHED or timeout."""
    for _ in range(MAX_POLL_ATTEMPTS):
        resp = requests.get(
            f'{GRAPH_API}/{container_id}',
            params={
                'fields': 'status_code',
                'access_token': access_token,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            status = resp.json().get('status_code')
            if status == 'FINISHED':
                return
            if status == 'ERROR':
                raise InstagramPublishError(
                    f'Container {container_id} entered ERROR state: {resp.json()}'
                )
        time.sleep(POLL_INTERVAL_SECONDS)

    raise InstagramPublishError(
        f'Container {container_id} not ready after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s'
    )
