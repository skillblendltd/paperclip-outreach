#!/usr/bin/env python3
"""
Merge existing UK scrape files into one comprehensive file.

Combines:
  - raw/uk_20260402.csv        (1,250 profiles with detailed data)
  - merged/uk_all_20260403.csv (6,060 profiles, partially scraped)

Priority: if both files have data for the same person, prefer the one with email.
Output: merged/uk_existing_combined.csv
"""

import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CSV_FIELDS = [
    "name", "email", "phone", "company", "chapter", "city",
    "postcode", "country", "specialty", "website", "address",
    "professional_details", "profile_url"
]

FILE_A = SCRIPT_DIR / "output" / "raw" / "uk_20260402.csv"
FILE_B = SCRIPT_DIR / "output" / "merged" / "uk_all_20260403.csv"
OUTPUT = SCRIPT_DIR / "output" / "merged" / "uk_existing_combined.csv"


def has_data(row):
    """Check if a row has meaningful profile data beyond just name/country/url."""
    return bool(row.get("email", "").strip() or row.get("phone", "").strip())


def row_quality(row):
    """Score a row by how much data it has."""
    score = 0
    for field in ["email", "phone", "company", "chapter", "city", "postcode",
                   "specialty", "website", "address", "professional_details"]:
        if row.get(field, "").strip():
            score += 1
    return score


def load_csv(path):
    if not path.exists():
        print(f"  [!] File not found: {path}")
        return []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"  Loaded {len(rows)} rows from {path.name}")
    return rows


def main():
    # Load both files
    rows_a = load_csv(FILE_A)
    rows_b = load_csv(FILE_B)

    # Build lookup by name (lowercase) - keep best version of each
    merged = {}

    # Load file B first (larger, but many empty rows)
    for row in rows_b:
        key = row.get("name", "").strip().lower()
        if key:
            merged[key] = row

    # Override with file A where it has better data
    upgraded = 0
    for row in rows_a:
        key = row.get("name", "").strip().lower()
        if not key:
            continue
        existing = merged.get(key)
        if not existing or row_quality(row) > row_quality(existing):
            merged[key] = row
            if existing:
                upgraded += 1

    # Also merge field-by-field: if A has email but B has company, combine
    # Re-load and do a second pass for field merging
    lookup_a = {}
    for row in rows_a:
        key = row.get("name", "").strip().lower()
        if key:
            lookup_a[key] = row

    lookup_b = {}
    for row in rows_b:
        key = row.get("name", "").strip().lower()
        if key:
            lookup_b[key] = row

    for key in merged:
        a = lookup_a.get(key, {})
        b = lookup_b.get(key, {})
        combined = {}
        for field in CSV_FIELDS:
            # Take the non-empty value, preferring A (higher quality file)
            val_a = a.get(field, "").strip()
            val_b = b.get(field, "").strip()
            combined[field] = val_a or val_b
        merged[key] = combined

    # Sort alphabetically by name
    contacts = sorted(merged.values(), key=lambda r: r.get("name", "").lower())

    # Save
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for c in contacts:
            writer.writerow({k: c.get(k, "") for k in CSV_FIELDS})

    # Stats
    total = len(contacts)
    with_email = sum(1 for c in contacts if c.get("email", "").strip())
    without_email = total - with_email
    with_phone = sum(1 for c in contacts if c.get("phone", "").strip())

    print(f"\n  Combined: {total} unique contacts")
    print(f"  With email: {with_email}")
    print(f"  Without email: {without_email} (will be re-scraped)")
    print(f"  With phone: {with_phone}")
    print(f"  Upgraded from file A: {upgraded}")
    print(f"  Saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
