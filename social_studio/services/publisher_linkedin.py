"""
LinkedIn publisher — UGC post creation with optional image asset upload.

The 3-step image upload flow:
    1. POST /v2/assets?action=registerUpload  → returns asset URN + upload URL
    2. PUT <upload URL> with PNG bytes
    3. POST /v2/ugcPosts with shareMediaCategory=IMAGE + asset URN

If the post has no `media_path`, falls back to text-only UGC post.

See docs/social-studio-v1-plan.md §9.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

LINKEDIN_API = 'https://api.linkedin.com/v2'
UGC_ENDPOINT = f'{LINKEDIN_API}/ugcPosts'
ASSETS_ENDPOINT = f'{LINKEDIN_API}/assets'
COMMENTS_ENDPOINT = f'{LINKEDIN_API}/socialActions'
FEEDSHARE_IMAGE_RECIPE = 'urn:li:digitalmediaRecipe:feedshare-image'


class LinkedInPublishError(Exception):
    """Raised when LinkedIn API rejects a request."""


def publish_post(account, post) -> Tuple[Optional[str], Optional[str]]:
    """Publish a SocialPost to a LinkedIn company page.

    Returns (platform_post_id, error_message). Exactly one will be None.
    Resolves `media_path` on the SocialPost to find an image to attach.
    """
    access_token = account.access_token or getattr(settings, 'LINKEDIN_ACCESS_TOKEN', '')
    org_id = account.page_id or getattr(settings, 'LINKEDIN_ORGANIZATION_ID', '')

    if not access_token or not org_id:
        return None, 'Missing access_token or page_id'

    body = post.content
    if post.hashtags:
        body += f'\n\n{post.hashtags}'

    media_asset_urn: Optional[str] = None
    image_path = _resolve_image_path(post)
    if image_path and image_path.exists():
        try:
            media_asset_urn = _upload_image_asset(access_token, org_id, image_path)
        except LinkedInPublishError as exc:
            return None, f'Image upload failed: {exc}'

    try:
        post_urn = _create_ugc_post(
            access_token=access_token,
            org_id=org_id,
            body=body,
            media_asset_urn=media_asset_urn,
        )
    except LinkedInPublishError as exc:
        return None, str(exc)

    # Best-effort first comment with link URL (non-fatal)
    if post.link_url:
        try:
            _post_first_comment(access_token, org_id, post_urn, post.link_url)
        except requests.RequestException:
            logger.warning('First-comment post failed for %s', post_urn)

    return post_urn, None


def _resolve_image_path(post) -> Optional[Path]:
    if not post.media_path:
        return None
    base = Path(settings.BASE_DIR) / 'social_studio'
    return (base / post.media_path).resolve()


def _auth_headers(access_token: str) -> dict:
    return {
        'Authorization': f'Bearer {access_token}',
        'X-Restli-Protocol-Version': '2.0.0',
    }


def _upload_image_asset(access_token: str, org_id: str, image_path: Path) -> str:
    """Run the LinkedIn 3-step image upload. Returns the asset URN."""
    owner_urn = f'urn:li:organization:{org_id}'

    register_payload = {
        'registerUploadRequest': {
            'recipes': [FEEDSHARE_IMAGE_RECIPE],
            'owner': owner_urn,
            'serviceRelationships': [{
                'relationshipType': 'OWNER',
                'identifier': 'urn:li:userGeneratedContent',
            }],
        }
    }

    headers = _auth_headers(access_token) | {'Content-Type': 'application/json'}
    register_resp = requests.post(
        f'{ASSETS_ENDPOINT}?action=registerUpload',
        json=register_payload,
        headers=headers,
        timeout=30,
    )
    if register_resp.status_code not in (200, 201):
        raise LinkedInPublishError(
            f'registerUpload HTTP {register_resp.status_code}: {register_resp.text[:300]}'
        )

    register_data = register_resp.json().get('value', {})
    upload_url = (
        register_data
        .get('uploadMechanism', {})
        .get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {})
        .get('uploadUrl')
    )
    asset_urn = register_data.get('asset')

    if not upload_url or not asset_urn:
        raise LinkedInPublishError(f'registerUpload missing uploadUrl/asset: {register_data}')

    with open(image_path, 'rb') as fh:
        image_bytes = fh.read()

    upload_resp = requests.put(
        upload_url,
        data=image_bytes,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=60,
    )
    if upload_resp.status_code not in (200, 201):
        raise LinkedInPublishError(
            f'Asset PUT HTTP {upload_resp.status_code}: {upload_resp.text[:300]}'
        )

    return asset_urn


def _create_ugc_post(
    *,
    access_token: str,
    org_id: str,
    body: str,
    media_asset_urn: Optional[str],
) -> str:
    """Create the UGC post and return the post URN."""
    share_content = {
        'shareCommentary': {'text': body},
        'shareMediaCategory': 'NONE',
    }

    if media_asset_urn:
        share_content['shareMediaCategory'] = 'IMAGE'
        share_content['media'] = [{
            'status': 'READY',
            'media': media_asset_urn,
        }]

    payload = {
        'author': f'urn:li:organization:{org_id}',
        'lifecycleState': 'PUBLISHED',
        'specificContent': {
            'com.linkedin.ugc.ShareContent': share_content,
        },
        'visibility': {
            'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC',
        },
    }

    headers = _auth_headers(access_token) | {'Content-Type': 'application/json'}
    resp = requests.post(UGC_ENDPOINT, json=payload, headers=headers, timeout=30)

    if resp.status_code not in (200, 201):
        raise LinkedInPublishError(f'ugcPosts HTTP {resp.status_code}: {resp.text[:500]}')

    post_urn = resp.json().get('id', '')
    if not post_urn:
        raise LinkedInPublishError(f'ugcPosts returned no id: {resp.json()}')
    return post_urn


def _post_first_comment(access_token: str, org_id: str, post_urn: str, text: str) -> None:
    headers = _auth_headers(access_token) | {'Content-Type': 'application/json'}
    requests.post(
        f'{COMMENTS_ENDPOINT}/{post_urn}/comments',
        json={
            'actor': f'urn:li:organization:{org_id}',
            'message': {'text': text},
        },
        headers=headers,
        timeout=15,
    )
