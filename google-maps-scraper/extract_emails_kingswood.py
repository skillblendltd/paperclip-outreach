#!/usr/bin/env python3
"""
Extract emails from Kingswood businesses that have websites but no email.
"""
import csv
import sys
import time
import os
import multiprocessing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CSV_FILE = os.path.join(os.path.dirname(__file__), "output", "kingswood_d22.csv")
DELAY = 2.0
SITE_TIMEOUT = 30


def _extract_one(website, result_queue):
    """Run in a child process so it can be killed if it hangs."""
    try:
        from email_extractor import EmailExtractor
        extractor = EmailExtractor()
        email = extractor.extract_email(website)
        extractor.close()
        result_queue.put(email)
    except Exception:
        result_queue.put(None)


def extract_with_timeout(website):
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=_extract_one, args=(website, q))
    p.start()
    p.join(timeout=SITE_TIMEOUT)
    if p.is_alive():
        p.kill()
        p.join()
        return None
    try:
        return q.get_nowait()
    except Exception:
        return None


def main():
    with open(CSV_FILE, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    need_email = [r for r in rows if r.get('website') and not r.get('email')]
    print(f'Total: {len(rows)} | Need email extraction: {len(need_email)}')

    extracted = 0
    for i, r in enumerate(need_email):
        website = r['website']
        if not website.startswith('http'):
            website = 'https://' + website

        email = extract_with_timeout(website)
        if email:
            r['email'] = email
            extracted += 1
            print(f'  [{i+1}/{len(need_email)}] {r["business_name"]}: {email}')

        if (i + 1) % 25 == 0:
            with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            print(f'  Saved ({extracted} emails so far from {i+1} sites)')

        time.sleep(DELAY)

    # Final save
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f'\nDone. Extracted {extracted} emails from {len(need_email)} websites.')


if __name__ == '__main__':
    main()
