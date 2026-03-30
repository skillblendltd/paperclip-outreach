#!/usr/bin/env python3
"""
Google Maps Scraper — Free Playwright-based, no API key needed.
Searches Google Maps for print/promo/embroidery shops,
enriches with website/phone, then extracts emails.

Usage:
    python scrape_maps.py                                           # Run all queries from config
    python scrape_maps.py --query "print shop" --location "Dublin"  # Single query
    python scrape_maps.py --max 20                                  # Limit results per query
    python scrape_maps.py --skip-emails                             # Skip email extraction
    python scrape_maps.py --skip-enrich                             # Skip detail enrichment
    python scrape_maps.py --resume                                  # Resume from existing output
    python scrape_maps.py --output ireland_shops                    # Custom output name
    python scrape_maps.py --headed                                  # Show browser (debug)
"""

import argparse
import csv
import importlib
import json
import os
import sys
import time
from datetime import datetime

from places_client import PlacesClient
from email_extractor import EmailExtractor


CSV_FIELDS = [
    "business_name", "email", "phone", "website", "address",
    "city", "region", "rating", "review_count", "business_category",
    "opening_hours", "segment", "source_query",
    "google_maps_url", "place_id", "latitude", "longitude",
]


def save_csv(results, filepath):
    """Save results to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def save_json(results, filepath):
    """Save results to JSON."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)


def load_existing(filepath):
    """Load existing CSV for resume mode."""
    if not os.path.exists(filepath):
        return []
    results = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(dict(row))
    return results


def deduplicate(results):
    """Remove duplicates by (business_name, address) pair."""
    seen = set()
    unique = []
    dupes = 0
    for r in results:
        key = (r["business_name"].lower().strip(), r.get("address", "").lower().strip())
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        unique.append(r)
    if dupes:
        print(f"  [i] Removed {dupes} duplicates")
    return unique


def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps for print/promo/embroidery shops (FREE)")
    parser.add_argument("--query", "-q", help="Single search keyword (e.g., 'promotional products')")
    parser.add_argument("--location", "-l", help="Single location (e.g., 'Dublin, Ireland')")
    parser.add_argument("--max", "-m", type=int, default=40, help="Max results per query (default: 40)")
    parser.add_argument("--skip-emails", action="store_true", help="Skip website email extraction")
    parser.add_argument("--skip-enrich", action="store_true", help="Skip clicking into listings for details")
    parser.add_argument("--resume", action="store_true", help="Resume from existing output file")
    parser.add_argument("--output", "-o", default=None, help="Custom output filename (without path)")
    parser.add_argument("--headed", action="store_true", help="Show browser window (for debugging)")
    parser.add_argument("--config", "-c", default="config", help="Config module name (default: config, e.g. config_uk)")
    args = parser.parse_args()

    # Load config module
    cfg = importlib.import_module(args.config)
    SEARCH_QUERIES = cfg.SEARCH_QUERIES
    OUTPUT_DIR = cfg.OUTPUT_DIR
    WEBSITE_SCRAPE_DELAY = cfg.WEBSITE_SCRAPE_DELAY

    # Determine search queries
    if args.query and args.location:
        queries = [{"keyword": args.query, "location": args.location}]
    elif args.query or args.location:
        parser.error("Both --query and --location are required for a single search")
        return
    else:
        queries = SEARCH_QUERIES

    # Output paths
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    base_name = args.output or f"maps_results_{timestamp}"
    if base_name.endswith(".csv"):
        base_name = base_name[:-4]
    csv_path = os.path.join(OUTPUT_DIR, f"{base_name}.csv")
    json_path = os.path.join(OUTPUT_DIR, f"{base_name}.json")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Phase 1: Search Google Maps ───────────────────────
    print(f"\n{'='*60}")
    print(f"  Google Maps Scraper (FREE — Playwright)")
    print(f"  Queries: {len(queries)} | Max per query: {args.max}")
    print(f"{'='*60}\n")

    # Resume mode
    existing_results = []
    searched_queries = set()
    if args.resume:
        existing_results = load_existing(csv_path)
        searched_queries = {r.get("source_query", "") for r in existing_results}
        print(f"  [i] Resuming: {len(existing_results)} existing results loaded\n")

    client = PlacesClient(headless=not args.headed)
    all_results = list(existing_results)

    try:
        for i, q in enumerate(queries, 1):
            query_str = f"{q['keyword']} in {q['location']}"
            if query_str in searched_queries:
                print(f"  [{i}/{len(queries)}] SKIP (already done): {query_str}")
                continue

            print(f"  [{i}/{len(queries)}] Searching: {query_str} ...", end=" ", flush=True)
            results = client.text_search(q["keyword"], q["location"], max_results=args.max)
            print(f"-> {len(results)} results")
            all_results.extend(results)

            # Save progress after each query
            save_csv(all_results, csv_path)

            time.sleep(2)  # pause between queries

    except KeyboardInterrupt:
        print("\n\n  [!] Search interrupted — saving progress...")

    # Deduplicate
    print(f"\n  Total raw results: {len(all_results)}")
    all_results = deduplicate(all_results)
    print(f"  After dedup: {len(all_results)}")

    save_csv(all_results, csv_path)
    save_json(all_results, json_path)
    print(f"  Saved to: {csv_path}")

    # ── Phase 2: Enrich with website/phone (click into each listing) ──
    if args.skip_enrich:
        print("\n  [i] Skipping detail enrichment (--skip-enrich)")
    else:
        needs_enrich = [r for r in all_results if not r.get("website") and r.get("google_maps_url")]
        if not needs_enrich:
            print("\n  [i] All listings already have websites")
        else:
            print(f"\n  Enriching {len(needs_enrich)} listings (fetching website/phone)...\n")
            try:
                client.enrich_with_details(all_results)
            except KeyboardInterrupt:
                print("\n\n  [!] Enrichment interrupted — saving progress...")

            save_csv(all_results, csv_path)
            save_json(all_results, json_path)

            with_website = sum(1 for r in all_results if r.get("website"))
            print(f"\n  After enrichment: {with_website}/{len(all_results)} have websites")

    # Close the maps browser
    client.close()

    # ── Phase 3: Extract Emails from Websites ─────────────
    if args.skip_emails:
        print("\n  [i] Skipping email extraction (--skip-emails)")
    else:
        needs_email = [r for r in all_results if r.get("website") and not r.get("email")]
        if not needs_email:
            print("\n  [i] No websites to scrape for emails")
        else:
            print(f"\n  Extracting emails from {len(needs_email)} websites...\n")
            extractor = EmailExtractor()
            found_count = 0

            try:
                email_idx = 0
                for idx, result in enumerate(all_results):
                    if not result.get("website") or result.get("email"):
                        continue

                    email_idx += 1
                    name = result["business_name"][:40]
                    print(f"  [{email_idx}/{len(needs_email)}] {name}...", end=" ", flush=True)

                    email = extractor.extract_email(result["website"])
                    if email:
                        result["email"] = email
                        found_count += 1
                        print(f"-> {email}")
                    else:
                        print("-> no email found")

                    # Save progress every 10
                    if email_idx % 10 == 0:
                        save_csv(all_results, csv_path)
                        save_json(all_results, json_path)

                    time.sleep(WEBSITE_SCRAPE_DELAY)

            except KeyboardInterrupt:
                print("\n\n  [!] Interrupted — saving progress...")
            finally:
                extractor.close()
                save_csv(all_results, csv_path)
                save_json(all_results, json_path)

            print(f"\n  Emails found: {found_count}/{len(needs_email)} websites scraped")

    # ── Summary ───────────────────────────────────────────
    with_email = sum(1 for r in all_results if r.get("email"))
    with_phone = sum(1 for r in all_results if r.get("phone"))
    with_website = sum(1 for r in all_results if r.get("website"))

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  Total businesses: {len(all_results)}")
    print(f"  With email:       {with_email} ({100*with_email//max(len(all_results),1)}%)")
    print(f"  With phone:       {with_phone} ({100*with_phone//max(len(all_results),1)}%)")
    print(f"  With website:     {with_website} ({100*with_website//max(len(all_results),1)}%)")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
