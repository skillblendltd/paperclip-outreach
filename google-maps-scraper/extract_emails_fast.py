#!/usr/bin/env python3
"""
Fast email extractor using requests (no Playwright, no hanging).
Fetches HTML, regex-extracts emails. Much faster and never hangs.

Usage: python extract_emails_fast.py output/kingswood_d22.csv
"""
import csv
import re
import sys
import time
import os
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

SKIP_DOMAINS = {
    'example.com', 'sentry.io', 'googleapis.com', 'google.com',
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'w3.org',
    'schema.org', 'wix.com', 'squarespace.com', 'wordpress.com',
    'cloudflare.com', 'amazonaws.com', 'github.com', 'apple.com',
}

SKIP_PREFIXES = ['noreply', 'no-reply', 'mailer', 'support@wix', 'email@example']

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})


def extract_email_from_url(url):
    """Fetch page HTML and extract first valid email."""
    try:
        resp = SESSION.get(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return None

        text = resp.text[:50000]  # Only check first 50KB
        emails = EMAIL_RE.findall(text)

        for email in emails:
            email = email.lower().strip()
            domain = email.split('@')[1] if '@' in email else ''

            if domain in SKIP_DOMAINS:
                continue
            if any(email.startswith(p) for p in SKIP_PREFIXES):
                continue
            if email.endswith('.png') or email.endswith('.jpg') or email.endswith('.svg'):
                continue

            return email

        # Try /contact page too
        base = resp.url.rstrip('/')
        for path in ['/contact', '/contact-us', '/about']:
            try:
                resp2 = SESSION.get(base + path, timeout=8, allow_redirects=True)
                if resp2.status_code == 200:
                    emails2 = EMAIL_RE.findall(resp2.text[:30000])
                    for email in emails2:
                        email = email.lower().strip()
                        domain = email.split('@')[1] if '@' in email else ''
                        if domain not in SKIP_DOMAINS and not any(email.startswith(p) for p in SKIP_PREFIXES):
                            if not email.endswith(('.png', '.jpg', '.svg')):
                                return email
            except Exception:
                pass

    except Exception:
        pass

    return None


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'output/kingswood_d22.csv'

    with open(csv_file, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    need_email = [(i, r) for i, r in enumerate(rows) if r.get('website') and not r.get('email')]
    print(f'Total: {len(rows)} | Need email extraction: {len(need_email)}')

    extracted = 0

    for count, (idx, r) in enumerate(need_email):
        website = r['website']
        if not website.startswith('http'):
            website = 'https://' + website

        email = extract_email_from_url(website)
        if email:
            rows[idx]['email'] = email
            extracted += 1
            print(f'  [{count+1}/{len(need_email)}] {r["business_name"]}: {email}')

        # Save every 100 records
        if (count + 1) % 100 == 0:
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            print(f'  --- Saved ({extracted} emails from {count+1} sites) ---')

    # Final save
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f'\nDone. Extracted {extracted} emails from {len(need_email)} websites.')


if __name__ == '__main__':
    main()
