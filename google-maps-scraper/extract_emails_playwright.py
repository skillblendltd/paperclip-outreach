#!/usr/bin/env python3
"""
Playwright-based email extractor with strict per-site timeout.
Uses subprocess to isolate each site - if it hangs, the subprocess is killed.

Usage: python extract_emails_playwright.py output/dublin_construction.csv
"""
import csv
import subprocess
import sys
import os
import time
import json

SITE_TIMEOUT = 25  # seconds per site
SAVE_EVERY = 50
DELAY = 1.0

# Inline script that Playwright runs per-site
EXTRACT_SCRIPT = '''
import sys, json
from email_extractor import EmailExtractor
try:
    extractor = EmailExtractor()
    email = extractor.extract_email(sys.argv[1])
    extractor.close()
    print(json.dumps({"email": email}))
except Exception as e:
    print(json.dumps({"email": None, "error": str(e)}))
'''


def extract_one(website, python_path, script_dir):
    """Run Playwright extraction in a subprocess with timeout."""
    try:
        result = subprocess.run(
            [python_path, '-c', EXTRACT_SCRIPT, website],
            capture_output=True,
            text=True,
            timeout=SITE_TIMEOUT,
            cwd=script_dir,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip().split('\n')[-1])
            return data.get('email')
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return None


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'output/dublin_construction.csv'
    python_path = sys.executable
    script_dir = os.path.dirname(os.path.abspath(__file__))

    with open(csv_file, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    need_email = [(i, r) for i, r in enumerate(rows) if r.get('website') and not r.get('email')]
    already = sum(1 for r in rows if r.get('email'))
    print(f'Total: {len(rows)} | Already have email: {already} | Need extraction: {len(need_email)}')
    sys.stdout.flush()

    extracted = 0
    for count, (idx, r) in enumerate(need_email):
        website = r['website']
        if not website.startswith('http'):
            website = 'https://' + website

        # Skip social media and known non-email sites
        skip_domains = ['facebook.com', 'instagram.com', 'twitter.com', 'linkedin.com',
                       'youtube.com', 'tiktok.com', 'pinterest.com', 'google.com']
        if any(d in website.lower() for d in skip_domains):
            continue

        email = extract_one(website, python_path, script_dir)
        if email:
            # Filter junk
            junk = ['example.com', 'domain.com', 'wix.com', 'squarespace.com', 'sentry.io',
                    'wordpress.com', 'cloudflare.com']
            if not any(j in email.lower() for j in junk) and not email.endswith(('.png', '.jpg', '.svg')):
                rows[idx]['email'] = email
                extracted += 1
                print(f'  [{count+1}/{len(need_email)}] {r["business_name"]}: {email}')
                sys.stdout.flush()

        # Save periodically
        if (count + 1) % SAVE_EVERY == 0:
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            print(f'  --- Saved ({already + extracted} total emails from {count+1} sites) ---')
            sys.stdout.flush()

        time.sleep(DELAY)

    # Final save
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f'\nDone. Extracted {extracted} new emails from {len(need_email)} websites.')
    print(f'Total emails in file: {already + extracted}')


if __name__ == '__main__':
    main()
