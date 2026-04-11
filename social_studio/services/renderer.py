"""
HTML → PNG renderer for social posts.

Takes a self-contained HTML file (authored by /taggiq-ui-designer or derived
from a starter template) and renders it to a 1200×1200 PNG via Playwright
Chromium. The caller owns the HTML; this service just produces pixels.

Design notes:
- Canvas is LinkedIn feed-square (1200×1200) at 2x device pixel ratio
- `networkidle` + `document.fonts.ready` ensures fonts + images finish loading
- `file://` navigation works as long as the HTML references assets by
  absolute path (starter templates use {% static %} with STATIC_ROOT pointing
  into social_studio/static/social/taggiq/)

See docs/social-studio-v1-plan.md §7 for rationale.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from django.conf import settings


CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 1200
DEVICE_SCALE_FACTOR = 2


def render_html_to_png(
    html_path: Path,
    out_path: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
    scale: int = DEVICE_SCALE_FACTOR,
) -> Path:
    """Render an HTML file to a PNG at the given canvas dimensions.

    Args:
        html_path: Absolute path to the HTML file to render.
        out_path: Where to write the PNG. Parent dirs will be created.
        width: Canvas width in CSS pixels.
        height: Canvas height in CSS pixels.
        scale: Device pixel ratio (2 = retina, produces 2400×2400 pixel PNG).

    Returns:
        The `out_path` it wrote to.

    Raises:
        FileNotFoundError: if `html_path` does not exist.
        RuntimeError: if Playwright screenshot fails.
    """
    html_path = Path(html_path).resolve()
    out_path = Path(out_path)

    if not html_path.exists():
        raise FileNotFoundError(f'HTML source not found: {html_path}')

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Deferred import so non-rendering code paths don't pay Playwright's load cost
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=['--no-sandbox'])
        try:
            context = browser.new_context(
                viewport={'width': width, 'height': height},
                device_scale_factor=scale,
            )
            page = context.new_page()
            page.goto(f'file://{html_path}', wait_until='networkidle')
            page.wait_for_function('document.fonts.ready')
            page.screenshot(
                path=str(out_path),
                clip={'x': 0, 'y': 0, 'width': width, 'height': height},
                omit_background=False,
                full_page=False,
            )
        finally:
            browser.close()

    return out_path


def resolve_post_html(post) -> Optional[Path]:
    """Resolve a SocialPost's bespoke HTML path to an absolute filesystem path.

    Returns None if the post has no bespoke HTML assigned.
    """
    if not post.bespoke_html_path:
        return None

    base = Path(settings.BASE_DIR) / 'social_studio'
    return (base / post.bespoke_html_path).resolve()


def default_png_path_for(post) -> Path:
    """Compute the default PNG output path for a SocialPost."""
    base = Path(settings.BASE_DIR) / 'social_studio'
    return (base / 'rendered_images' / f'post_{post.post_number:02d}.png').resolve()
