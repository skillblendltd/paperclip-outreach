#!/usr/bin/env python3
"""
Simple email extractor - no multiprocessing, just sequential with signal timeout.
Usage: python extract_emails_simple.py output/kingswood_d22.csv
"""
import csv
import signal
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from email_extractor import EmailExtractor


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError()


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "output", "kingswood_d22.csv")

    with open(csv_file, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    need_email = [(i, r) for i, r in enumerate(rows) if r.get('website') and not r.get('email')]
    print(f'Total: {len(rows)} | Need email extraction: {len(need_email)}')

    extractor = EmailExtractor()
    extracted = 0

    for count, (idx, r) in enumerate(need_email):
        website = r['website']
        if not website.startswith('http'):
            website = 'https://' + website

        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(20)  # 20 second timeout
            email = extractor.extract_email(website)
            signal.alarm(0)

            if email:
                rows[idx]['email'] = email
                extracted += 1
                print(f'  [{count+1}/{len(need_email)}] {r["business_name"]}: {email}')
        except TimeoutError:
            signal.alarm(0)
        except Exception:
            signal.alarm(0)

        # Save every 50 records
        if (count + 1) % 50 == 0:
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            print(f'  --- Saved ({extracted} emails from {count+1} sites) ---')

        time.sleep(1)

    # Final save
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    extractor.close()
    print(f'\nDone. Extracted {extracted} emails from {len(need_email)} websites.')


if __name__ == '__main__':
    main()
