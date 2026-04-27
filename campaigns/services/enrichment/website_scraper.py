"""
Website team/about page scraper.
Visits prospect websites to extract owner/director names from
/about, /team, /our-team, /meet-the-team pages.

Uses Claude (via subprocess) to parse unstructured HTML into
structured owner data. Falls back to regex patterns if Claude
is unavailable.
"""

import json
import logging
import re
import subprocess
import time
from urllib.parse import urljoin, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Pages to check for team/owner info (in order of priority)
TEAM_PATHS = [
    "/about", "/about-us", "/team",
]

# Regex patterns for owner/director mentions
OWNER_PATTERNS = [
    # "Founded by John Murphy" or "Established by..."
    re.compile(r'(?:founded|established|started|created)\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})', re.IGNORECASE),
    # "John Murphy, Owner" or "John Murphy - Managing Director"
    re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[,\-]\s*(?:Owner|Founder|Director|Managing Director|MD|CEO|Proprietor)', re.IGNORECASE),
    # "Owner: John Murphy"
    re.compile(r'(?:Owner|Founder|Director|Managing Director|MD|CEO|Proprietor)\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})', re.IGNORECASE),
]

# Title patterns to extract alongside names
TITLE_PATTERNS = re.compile(
    r'(?:Owner|Founder|Co-Founder|Director|Managing Director|MD|CEO|'
    r'Proprietor|Principal|General Manager|Creative Director)',
    re.IGNORECASE,
)


def _dismiss_consent(page):
    """Try to click common cookie consent buttons."""
    consent_selectors = [
        'button:has-text("Accept")',
        'button:has-text("Accept All")',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Got it")',
        'button:has-text("OK")',
        'a:has-text("Accept")',
        '.cc-dismiss', '.cc-accept', '.cc-allow',
        '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
        '[data-action="accept"]',
    ]
    for sel in consent_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=500):
                btn.click(timeout=1000)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def _clean_website_url(website_url):
    """Strip UTM params and normalize a website URL."""
    if not website_url:
        return None
    if not website_url.startswith("http"):
        website_url = "https://" + website_url
    parsed = urlparse(website_url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).rstrip("/")


def scrape_team_pages(website_url, page=None):
    """
    Visit a business website and scrape team/about pages.
    Returns the combined text content from relevant pages.

    If `page` is provided, reuse that Playwright page (batch mode).
    Otherwise, launch a fresh browser (single-use mode).
    """
    from playwright.sync_api import sync_playwright

    website_url = _clean_website_url(website_url)
    if not website_url:
        return None

    combined_text = ""
    own_browser = page is None

    try:
        if own_browser:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

        # First try the homepage itself
        pages_to_try = [website_url] + [
            urljoin(website_url + "/", path.lstrip("/"))
            for path in TEAM_PATHS
        ]

        for url in pages_to_try:
            try:
                resp = page.goto(url, timeout=7000, wait_until="domcontentloaded")
                if resp and resp.status == 200:
                    # Dismiss cookie consent popups
                    _dismiss_consent(page)

                    # Get visible text content (not full HTML)
                    text = page.evaluate("""() => {
                        // Remove scripts, styles, nav, footer, cookie banners
                        const removeSelectors = [
                            'script', 'style', 'nav', 'footer', 'header',
                            '[class*="cookie"]', '[class*="consent"]', '[class*="gdpr"]',
                            '[id*="cookie"]', '[id*="consent"]', '[id*="gdpr"]',
                            '.cc-banner', '.cookie-bar', '#CybotCookiebotDialog',
                        ];
                        removeSelectors.forEach(sel => {
                            try { document.querySelectorAll(sel).forEach(el => el.remove()); }
                            catch(e) {}
                        });
                        return document.body ? document.body.innerText : '';
                    }""")
                    if text and len(text) > 50:
                        # Skip pages that are mostly cookie/consent text
                        lower = text.lower()
                        if lower.count("cookie") > 5 or lower.count("consent") > 3:
                            continue
                        combined_text += f"\n--- {url} ---\n{text[:5000]}\n"
                time.sleep(0.3)
            except Exception:
                continue

        if own_browser:
            context.close()
            browser.close()
            pw.stop()

    except Exception as e:
        logger.error("Website scrape failed for %s: %s", website_url, e)
        return None

    return combined_text if combined_text else None


def extract_owner_regex(text):
    """
    Try to extract owner/director name using regex patterns.
    Returns dict {name, title} or None.
    """
    if not text:
        return None

    for pattern in OWNER_PATTERNS:
        match = pattern.search(text)
        if match:
            name = match.group(1).strip()
            # Validate: must be 2-4 words, no common false positives
            words = name.split()
            if 2 <= len(words) <= 4:
                skip_words = {"the", "our", "this", "that", "your", "sign", "print", "about"}
                if words[0].lower() not in skip_words:
                    # Try to find a title near the match
                    context = text[max(0, match.start() - 50):match.end() + 50]
                    title_match = TITLE_PATTERNS.search(context)
                    title = title_match.group(0).title() if title_match else "Owner"
                    return {"name": name, "title": title}
    return None


def extract_owner_claude(text, business_name):
    """
    Use Claude CLI to extract owner/director from page text.
    Uses haiku for cost efficiency (~$0.003 per call).
    Returns dict {name, title} or None.
    """
    if not text or len(text) < 50:
        return None

    # Truncate to keep costs down
    text_truncated = text[:3000]

    prompt = (
        'From this website text, extract the name of any person who appears to be the '
        'owner, founder, director, manager, or key contact of "%s". '
        'Look for: names in About Us sections, names near titles like Owner/Founder/Director/MD/CEO, '
        'contact section names, email signatures, blog authors who write about the business, '
        'or names that could be derived from the domain/brand name. '
        'Return ONLY JSON: {"name": "John Murphy", "title": "Owner"} '
        'or {"name": null} if no person name found. No explanation.\n\n'
        'Website text:\n%s'
    ) % (business_name, text_truncated)

    try:
        result = subprocess.run(
            [
                "claude", "--model", "haiku",
                "--max-turns", "1",
                "--output-format", "text",
                "-p", prompt,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Claude CLI failed: %s", result.stderr[:200])
            return None

        output = result.stdout.strip()
        # Try to parse JSON from output
        # Claude might wrap it in ```json ... ```
        json_match = re.search(r'\{[^}]+\}', output)
        if json_match:
            data = json.loads(json_match.group())
            if data.get("name"):
                return {
                    "name": data["name"],
                    "title": data.get("title", "Owner"),
                }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning("Claude extraction failed for %s: %s", business_name, e)

    return None


def enrich_prospect(website_url, business_name, use_claude=True):
    """
    Main entry point: scrape website, extract owner name.
    Returns dict {name, title, source} or None.
    """
    text = scrape_team_pages(website_url)
    if not text:
        return None

    # Try regex first (free, instant)
    result = extract_owner_regex(text)
    if result:
        result["source"] = "website"
        return result

    # Fall back to Claude if enabled
    if use_claude:
        result = extract_owner_claude(text, business_name)
        if result:
            result["source"] = "website_ai"
            return result

    return None
