"""
Google Business Profile publisher - create local posts on a GBP listing.

Uses the Google My Business API v4:
    POST accounts/{account_id}/locations/{location_id}/localPosts

Auth: OAuth2 access token stored in SocialAccount.access_token.
The page_id on SocialAccount stores "account_id/location_id" (slash-separated).

Image: If the post has a media_url (public URL), it is included as a media
item. Local media_path is not supported directly (GBP requires a public URL).

See: https://developers.google.com/my-business/content/posts-data
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import requests


logger = logging.getLogger(__name__)

GBP_API = 'https://mybusinessbusinessinformation.googleapis.com/v1'
GBP_POSTS_API = 'https://mybusiness.googleapis.com/v4'


def publish_post(account, post) -> Tuple[Optional[str], Optional[str]]:
    """Publish a SocialPost as a Google Business Profile local post.

    Returns (platform_post_id, error_message). Exactly one will be None.

    account.page_id format: "accounts/{account_id}/locations/{location_id}"
    """
    access_token = account.access_token
    location_path = account.page_id  # e.g. "accounts/123/locations/456"

    if not access_token or not location_path:
        return None, 'Missing access_token or page_id (accounts/X/locations/Y) on SocialAccount'

    body = post.content
    if post.hashtags:
        body += f'\n\n{post.hashtags}'

    # GBP summary field has a 1500 char limit
    if len(body) > 1500:
        body = body[:1497] + '...'

    payload = {
        'languageCode': 'en',
        'summary': body,
        'topicType': 'STANDARD',
    }

    # Add image if available (requires public URL)
    image_url = post.media_url if post.media_url else ''
    if image_url:
        payload['media'] = [{
            'mediaFormat': 'PHOTO',
            'sourceUrl': image_url,
        }]

    # Add CTA button if link URL exists
    if post.link_url:
        payload['callToAction'] = {
            'actionType': 'LEARN_MORE',
            'url': post.link_url,
        }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(
            f'{GBP_POSTS_API}/{location_path}/localPosts',
            json=payload,
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as exc:
        return None, f'Request failed: {exc}'

    if resp.status_code not in (200, 201):
        return None, f'localPosts POST HTTP {resp.status_code}: {resp.text[:500]}'

    post_name = resp.json().get('name', '')
    if not post_name:
        return None, f'localPosts returned no name: {resp.json()}'

    return post_name, None
