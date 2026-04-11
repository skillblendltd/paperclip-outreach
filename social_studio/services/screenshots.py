"""
TaggIQ product screenshot capture.

Uses Playwright to open the running TaggIQ frontend (typically localhost:5180)
and screenshot specific routes for use as social post illustrations.

v1 scope: captures the routes listed in TAGGIQ_ROUTES. If routes require an
authenticated session, set TAGGIQ_SESSION_COOKIE in env before running.

Blocked pending Prakash providing demo credentials for authenticated views.
For now the service runs against whatever is publicly accessible.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from django.conf import settings


TAGGIQ_FRONTEND_URL = os.getenv('TAGGIQ_FRONTEND_URL', 'http://host.docker.internal:5180')

# Routes to capture. Add more as new product surfaces ship.
# Tuples of (slug, relative_url, viewport_size).
TAGGIQ_ROUTES: list[tuple[str, str, tuple[int, int]]] = [
    ('dashboard',       '/',                    (1440, 900)),
    ('quote-builder',   '/quotes/new',          (1440, 900)),
    ('supplier-search', '/products',            (1440, 900)),
    ('artwork-approval','/artworks',            (1440, 900)),
    ('invoicing',       '/invoices',            (1440, 900)),
]


def _output_dir() -> Path:
    return (Path(settings.BASE_DIR) / 'social_studio' / 'static' / 'taggiq-ui').resolve()


def capture_routes(
    routes: Iterable[tuple[str, str, tuple[int, int]]] = TAGGIQ_ROUTES,
    *,
    base_url: str = TAGGIQ_FRONTEND_URL,
    session_cookie: Optional[str] = None,
) -> dict:
    """Capture screenshots of TaggIQ product routes. Returns a summary dict."""
    from playwright.sync_api import sync_playwright

    out_dir = _output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    captured: list[str] = []
    failed: list[tuple[str, str]] = []

    session_cookie = session_cookie or os.getenv('TAGGIQ_SESSION_COOKIE', '')

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=['--no-sandbox'])
        try:
            for slug, path, viewport in routes:
                try:
                    context = browser.new_context(
                        viewport={'width': viewport[0], 'height': viewport[1]},
                        device_scale_factor=2,
                    )
                    if session_cookie:
                        # Attach session cookie to authenticate as a test user
                        from urllib.parse import urlparse
                        host = urlparse(base_url).hostname or 'localhost'
                        context.add_cookies([{
                            'name': 'sessionid',
                            'value': session_cookie,
                            'domain': host,
                            'path': '/',
                        }])

                    page = context.new_page()
                    page.goto(f'{base_url}{path}', wait_until='networkidle', timeout=20000)
                    out_path = out_dir / f'{slug}.png'
                    page.screenshot(path=str(out_path), full_page=False)
                    captured.append(slug)
                    context.close()
                except Exception as exc:
                    failed.append((slug, str(exc)[:200]))
        finally:
            browser.close()

    return {
        'captured': captured,
        'failed': failed,
        'out_dir': str(out_dir),
    }
