#!/usr/bin/env python3
"""
Merge raw BNI scrape files into deduplicated country masters and a global master.

Usage:
    python merge_countries.py --country uk       # Merge all uk_*.csv → uk_all.csv
    python merge_countries.py --all              # Rebuild global master from all country masters
    python merge_countries.py --stats            # Show stats for all merged files
"""

import argparse
import csv
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
RAW_DIR = SCRIPT_DIR / "output" / "raw"
MERGED_DIR = SCRIPT_DIR / "output" / "merged"

CSV_FIELDS = [
    "name", "email", "phone", "company", "chapter", "city",
    "postcode", "country", "specialty", "website", "address",
    "professional_details", "profile_url"
]


def extract_user_id(profile_url):
    """Extract userId from profile URL for deduplication."""
    m = re.search(r'userId=(\d+)', profile_url or '')
    return m.group(1) if m else None


def field_count(row):
    """Count non-empty fields in a row."""
    return sum(1 for v in row.values() if v and v.strip())


def merge_country(country_code):
    """Merge all raw CSVs for a country into a deduplicated master."""
    raw_files = sorted(RAW_DIR.glob(f"{country_code}_*.csv"))
    if not raw_files:
        print(f"No raw files found for '{country_code}' in {RAW_DIR}")
        return

    print(f"[*] Merging {len(raw_files)} file(s) for {country_code}:")
    for f in raw_files:
        print(f"    {f.name}")

    # Deduplicate by userId, keeping the record with most fields
    seen = {}  # userId -> row
    no_id = []  # rows without userId

    for raw_file in raw_files:
        with open(raw_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = extract_user_id(row.get("profile_url", ""))
                if uid:
                    if uid not in seen or field_count(row) > field_count(seen[uid]):
                        seen[uid] = row
                else:
                    no_id.append(row)

    all_rows = list(seen.values()) + no_id
    all_rows.sort(key=lambda r: r.get("name", ""))

    output = MERGED_DIR / f"{country_code}_all.csv"
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})

    emails = sum(1 for r in all_rows if r.get("email", "").strip())
    companies = sum(1 for r in all_rows if r.get("company", "").strip())
    dupes = sum(len(list(RAW_DIR.glob(f"{country_code}_*.csv")))) - 1
    print(f"[+] {output.name}: {len(all_rows)} contacts, {emails} emails, {companies} companies")
    if len(seen) < sum(1 for _ in _count_raw(raw_files)):
        print(f"    Deduped by userId")
    return output


def _count_raw(files):
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for _ in csv.DictReader(fh):
                yield 1


def merge_all():
    """Merge all country masters into a global master."""
    country_files = sorted(MERGED_DIR.glob("*_all.csv"))
    if not country_files:
        print("No country master files found. Run --country first.")
        return

    print(f"[*] Building global master from {len(country_files)} countries:")
    seen = {}
    for cf in country_files:
        count = 0
        with open(cf, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = extract_user_id(row.get("profile_url", ""))
                key = uid or row.get("email", "") or row.get("name", "")
                if key not in seen or field_count(row) > field_count(seen[key]):
                    seen[key] = row
                count += 1
        print(f"    {cf.name}: {count}")

    all_rows = sorted(seen.values(), key=lambda r: (r.get("country", ""), r.get("name", "")))
    output = MERGED_DIR / "bni_master.csv"
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})

    emails = sum(1 for r in all_rows if r.get("email", "").strip())
    countries = len({r.get("country", "") for r in all_rows if r.get("country", "").strip()})
    print(f"\n[+] Global master: {len(all_rows)} contacts, {emails} emails, {countries} countries")
    print(f"    File: {output}")


def show_stats():
    """Show stats for all merged files."""
    print(f"\n{'File':<30} {'Contacts':<10} {'Emails':<10} {'Companies':<10} {'Countries'}")
    print("-" * 80)
    for f in sorted(MERGED_DIR.glob("*.csv")):
        with open(f, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        emails = sum(1 for r in rows if r.get("email", "").strip())
        companies = sum(1 for r in rows if r.get("company", "").strip())
        countries = len({r.get("country", "") for r in rows if r.get("country", "").strip()})
        print(f"{f.name:<30} {len(rows):<10} {emails:<10} {companies:<10} {countries}")


def main():
    parser = argparse.ArgumentParser(description="Merge BNI scrape files")
    parser.add_argument("--country", type=str, help="Country code to merge (e.g. uk)")
    parser.add_argument("--all", action="store_true", help="Rebuild global master")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    args = parser.parse_args()

    MERGED_DIR.mkdir(parents=True, exist_ok=True)

    if args.stats:
        show_stats()
    elif args.country:
        merge_country(args.country)
    elif args.all:
        merge_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
