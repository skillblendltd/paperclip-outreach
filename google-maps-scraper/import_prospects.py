#!/usr/bin/env python3
"""
Import Google Maps scraper results into Django campaign system.
Same pattern as bni-scraper/import_promo_global.py.

Usage:
    python import_prospects.py --campaign-id <uuid> --csv output/maps_results.csv
    python import_prospects.py --campaign-id <uuid> --csv output/maps_results.csv --dry-run
    python import_prospects.py --campaign-id <uuid> --csv output/maps_results.csv --exclude-campaigns <uuid1> <uuid2>
"""

import argparse
import csv
import json
import sys
import urllib.request

from config import DJANGO_API_BASE, IMPORT_BATCH_SIZE


def fetch_existing_emails(campaign_ids):
    """Fetch emails from existing campaigns to avoid cross-campaign duplicates."""
    existing = set()
    for cid in campaign_ids:
        try:
            url = f"{DJANGO_API_BASE}/api/prospects/?campaign_id={cid}&limit=5000"
            resp = urllib.request.urlopen(url)
            data = json.loads(resp.read())
            prospects = data if isinstance(data, list) else data.get("results", data.get("prospects", []))
            for p in prospects:
                email = p.get("email", "").strip().lower()
                if email:
                    existing.add(email)
            print(f"  [i] Loaded {len(prospects)} prospects from campaign {cid[:8]}...")
        except Exception as e:
            print(f"  [!] Could not load campaign {cid[:8]}...: {e}")
    return existing


def build_prospect(row):
    """Convert a CSV row into a prospect dict for the import API."""
    email = row.get("email", "").strip()
    if not email or "@" not in email:
        return None

    business_name = row.get("business_name", "").strip()
    if not business_name:
        return None

    # Build notes from Google Maps data
    notes_parts = []
    if row.get("rating"):
        notes_parts.append(f"Google Rating: {row['rating']}")
    if row.get("review_count"):
        notes_parts.append(f"Reviews: {row['review_count']}")
    if row.get("business_category"):
        notes_parts.append(f"Category: {row['business_category']}")
    if row.get("source_query"):
        notes_parts.append(f"Found via: {row['source_query']}")
    if row.get("google_maps_url"):
        notes_parts.append(f"Maps: {row['google_maps_url']}")

    notes = " | ".join(notes_parts)

    return {
        "business_name": business_name,
        "email": email,
        "phone": row.get("phone", ""),
        "city": row.get("city", ""),
        "region": row.get("region", ""),
        "website": row.get("website", ""),
        "segment": row.get("segment", "promo_distributor"),
        "business_type": row.get("business_category", ""),
        "tier": "B",
        "score": 50,
        "notes": notes,
    }


def import_batch(campaign_id, prospects):
    """POST a batch of prospects to the Django import API."""
    payload = json.dumps({
        "campaign_id": campaign_id,
        "prospects": prospects,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{DJANGO_API_BASE}/api/import/",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [!] API error {e.code}: {body}")
        return None
    except Exception as e:
        print(f"  [!] Request failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Import Google Maps prospects into Django campaign")
    parser.add_argument("--campaign-id", "-c", required=True, help="Target campaign UUID")
    parser.add_argument("--csv", required=True, help="Path to CSV file from scrape_maps.py")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without importing")
    parser.add_argument(
        "--exclude-campaigns", nargs="*", default=[],
        help="Campaign UUIDs to check for existing emails (avoid cross-campaign dupes)"
    )
    args = parser.parse_args()

    # Load CSV
    try:
        with open(args.csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"  [!] CSV not found: {args.csv}")
        sys.exit(1)

    print(f"\n  Loaded {len(rows)} rows from {args.csv}")

    # Fetch existing emails to exclude
    exclude_emails = set()
    all_campaign_ids = [args.campaign_id] + args.exclude_campaigns
    exclude_emails = fetch_existing_emails(all_campaign_ids)
    print(f"  Excluding {len(exclude_emails)} existing emails\n")

    # Build prospect list
    prospects = []
    skipped_no_email = 0
    skipped_duplicate = 0

    for row in rows:
        prospect = build_prospect(row)
        if not prospect:
            skipped_no_email += 1
            continue

        if prospect["email"].lower() in exclude_emails:
            skipped_duplicate += 1
            continue

        prospects.append(prospect)
        exclude_emails.add(prospect["email"].lower())  # prevent intra-file dupes

    print(f"  Ready to import: {len(prospects)}")
    print(f"  Skipped (no email): {skipped_no_email}")
    print(f"  Skipped (duplicate): {skipped_duplicate}")

    if args.dry_run:
        print(f"\n  [DRY RUN] Would import {len(prospects)} prospects into campaign {args.campaign_id}")
        # Show first 5 as sample
        for p in prospects[:5]:
            print(f"    -> {p['business_name']} | {p['email']} | {p['city']}")
        if len(prospects) > 5:
            print(f"    ... and {len(prospects) - 5} more")
        return

    if not prospects:
        print("\n  Nothing to import.")
        return

    # Import in batches
    total_created = 0
    total_updated = 0
    total_skipped = 0

    for i in range(0, len(prospects), IMPORT_BATCH_SIZE):
        batch = prospects[i:i + IMPORT_BATCH_SIZE]
        batch_num = i // IMPORT_BATCH_SIZE + 1
        print(f"\n  Batch {batch_num}: importing {len(batch)} prospects...", end=" ", flush=True)

        result = import_batch(args.campaign_id, batch)
        if result:
            created = result.get("created", 0)
            updated = result.get("updated", 0)
            skipped = result.get("skipped", 0)
            total_created += created
            total_updated += updated
            total_skipped += skipped
            print(f"-> created: {created}, updated: {updated}, skipped: {skipped}")
        else:
            print("-> FAILED")

    print(f"\n  {'='*50}")
    print(f"  IMPORT COMPLETE")
    print(f"  Created:  {total_created}")
    print(f"  Updated:  {total_updated}")
    print(f"  Skipped:  {total_skipped}")
    print(f"  Campaign: {args.campaign_id}")
    print(f"  {'='*50}\n")


if __name__ == "__main__":
    main()
