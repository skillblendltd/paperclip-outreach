#!/usr/bin/env python3
"""
Extract emails from London borough businesses that have websites but no email.
Reads uk_london_boroughs_20260330.csv, visits websites, writes emails back.
"""

import csv
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CSV_FILE = "output/uk_london_boroughs_20260330.csv"
JSON_FILE = "output/uk_london_boroughs_20260330.json"
DELAY = 3.0


def main():
    # Load CSV
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []

    needs_email = [r for r in rows if r.get("website") and not r.get("email")]
    already_done = sum(1 for r in rows if r.get("email"))
    print(f"Total: {len(rows)} | Already have email: {already_done} | Need email extraction: {len(needs_email)}")
    print(f"Starting email extraction...\n")

    from email_extractor import EmailExtractor
    extractor = EmailExtractor()

    extracted = 0
    failed = 0

    try:
        for i, row in enumerate(needs_email):
            biz = row.get("business_name", "?")
            website = row["website"]
            print(f"  [{i+1}/{len(needs_email)}] {biz} ({website})...", end=" ", flush=True)

            try:
                email = extractor.extract_email(website)
                if email:
                    row["email"] = email
                    extracted += 1
                    print(f"✓ {email}")
                else:
                    failed += 1
                    print("no email found")
            except Exception as e:
                failed += 1
                print(f"ERROR: {e}")

            time.sleep(DELAY)

            # Save progress every 50 records
            if (i + 1) % 50 == 0:
                _save(rows, fieldnames)
                print(f"\n  [checkpoint] Saved progress ({i+1}/{len(needs_email)})\n")

    finally:
        extractor.close()
        _save(rows, fieldnames)
        print(f"\n{'=' * 60}")
        print(f"  DONE! Extracted: {extracted} | Failed: {failed}")
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
    main()
