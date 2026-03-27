"""
Email extractor — visits business websites and scrapes contact emails.
Uses Playwright (headless Chromium), same pattern as the BNI scraper.
"""

import re
import time
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from config import WEBSITE_SCRAPE_DELAY, WEBSITE_TIMEOUT, EMAIL_SKIP_PREFIXES, EMAIL_PREFERRED_PREFIXES


EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Pages to check for contact info (in order)
CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/get-in-touch"]


class EmailExtractor:
    """Scrapes emails from business websites using headless Playwright."""

    def __init__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

    def extract_email(self, website_url):
        """
        Visit a business website and try to find a contact email.
        Returns the best email found, or None.
        """
        if not website_url:
            return None

        # Ensure URL has scheme
        if not website_url.startswith("http"):
            website_url = "https://" + website_url

        all_emails = set()

        # Step 1: Check homepage
        emails = self._scrape_page(website_url)
        all_emails.update(emails)

        # Step 2: If no good email yet, try contact/about pages
        if not self._has_preferred_email(all_emails):
            for path in CONTACT_PATHS:
                try:
                    contact_url = urljoin(website_url.rstrip("/") + "/", path.lstrip("/"))
                    emails = self._scrape_page(contact_url)
                    all_emails.update(emails)
                    if self._has_preferred_email(all_emails):
                        break
                except Exception:
                    continue

        # Step 3: Filter and rank
        filtered = self._filter_emails(all_emails, website_url)
        if not filtered:
            return None

        return self._rank_emails(filtered)

    def _scrape_page(self, url):
        """Load a single page and extract all emails from it."""
        emails = set()
        page = None
        try:
            page = self._context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=WEBSITE_TIMEOUT)
            # Small wait for JS-rendered content
            page.wait_for_timeout(1500)

            # Method 1: mailto: links (most reliable)
            mailto_links = page.eval_on_selector_all(
                'a[href^="mailto:"]',
                "els => els.map(e => e.href.replace('mailto:', '').split('?')[0].trim())"
            )
            for email in mailto_links:
                if EMAIL_REGEX.match(email):
                    emails.add(email.lower())

            # Method 2: Regex on page text
            body_text = page.inner_text("body")
            for match in EMAIL_REGEX.findall(body_text):
                emails.add(match.lower())

            # Method 3: Check page source (catches hidden/obfuscated emails)
            page_source = page.content()
            for match in EMAIL_REGEX.findall(page_source):
                emails.add(match.lower())

        except PlaywrightTimeout:
            pass  # Site too slow, skip
        except Exception:
            pass  # Connection error, SSL error, etc.
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

        return emails

    def _filter_emails(self, emails, website_url):
        """Remove junk emails and emails from other domains."""
        domain = urlparse(website_url).netloc.replace("www.", "")
        filtered = []

        for email in emails:
            local_part = email.split("@")[0]
            email_domain = email.split("@")[1]

            # Skip known junk prefixes
            if any(local_part.startswith(prefix) for prefix in EMAIL_SKIP_PREFIXES):
                continue

            # Skip image/file extensions mistakenly caught by regex
            if email_domain.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")):
                continue

            # Skip very long emails (likely not real)
            if len(email) > 60:
                continue

            # Prefer emails matching the business domain
            # but accept all valid-looking emails
            filtered.append(email)

        # Sort: same-domain emails first
        filtered.sort(key=lambda e: 0 if domain in e else 1)
        return filtered

    def _rank_emails(self, emails):
        """Pick the best email from a filtered list."""
        # First: check for preferred prefixes
        for prefix in EMAIL_PREFERRED_PREFIXES:
            for email in emails:
                if email.split("@")[0] == prefix:
                    return email

        # Second: check for preferred prefixes as startswith
        for prefix in EMAIL_PREFERRED_PREFIXES:
            for email in emails:
                if email.split("@")[0].startswith(prefix):
                    return email

        # Default: return the first one
        return emails[0] if emails else None

    def _has_preferred_email(self, emails):
        """Check if we already found a preferred email."""
        for email in emails:
            local = email.split("@")[0]
            if any(local.startswith(p) for p in EMAIL_PREFERRED_PREFIXES):
                return True
        return False

    def close(self):
        """Clean up browser resources."""
        try:
            self._context.close()
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass
