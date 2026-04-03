#!/usr/bin/env python3
"""
Extract emails from Central London businesses that have websites but no email.
Reads uk_london_20260329.csv, visits websites, writes emails back.
Uses multiprocessing for hard per-site timeout (Playwright blocks SIGALRM).
"""

import csv
import json
import sys
import time
import os
import multiprocessing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CSV_FILE = "output/uk_london_20260329.csv"
JSON_FILE = "output/uk_london_20260329.json"
DELAY = 2.0
SITE_TIMEOUT = 60


def _extract_one(website, result_queue):
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
        return None, "TIMEOUT"
    try:
        email = q.get_nowait()
        return email, None
    except Exception:
        return None, "ERROR"


def main():
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []

    needs_email = [r for r in rows if r.get("website") and not r.get("email")]
    already_done = sum(1 for r in rows if r.get("email"))
    print(f"Total: {len(rows)} | Already have email: {already_done} | Need email extraction: {len(needs_email)}")
    print(f"Starting email extraction (timeout={SITE_TIMEOUT}s per site)...\n", flush=True)

    extracted = 0
    failed = 0
    timeouts = 0

    try:
        for i, row in enumerate(needs_email):
            biz = row.get("business_name", "?")
            website = row["website"]
            print(f"  [{i+1}/{len(needs_email)}] {biz} ({website})...", end=" ", flush=True)

            email, err = extract_with_timeout(website)

            if err == "TIMEOUT":
                timeouts += 1
                failed += 1
                print("TIMEOUT (killed)")
            elif email:
                row["email"] = email
                extracted += 1
                print(f"found: {email}")
            else:
                failed += 1
                print("no email found")

            time.sleep(DELAY)

            if (i + 1) % 50 == 0:
                _save(rows, fieldnames)
                print(f"\n  [checkpoint] Saved. Extracted: {extracted} | Failed: {failed} | Timeouts: {timeouts}\n", flush=True)

    finally:
        _save(rows, fieldnames)
        print(f"\n{'=' * 60}")
        print(f"  DONE! Extracted: {extracted} | Failed: {failed} | Timeouts: {timeouts}")
        print(f"  Total with email: {sum(1 for r in rows if r.get('email'))}/{len(rows)}")
        print(f"{'=' * 60}")


def _save(rows, fieldnames):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    main()
