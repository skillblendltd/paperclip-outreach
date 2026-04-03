#!/usr/bin/env python3
"""
Filter BNI contacts by specialty.

Usage:
    python filter_specialties.py --country uk --type print_promo   # UK print & promo people
    python filter_specialties.py --country uk --type print          # UK printers only
    python filter_specialties.py --file output/merged/uk_all.csv --type apparel
    python filter_specialties.py --country uk --type all            # All UK members (no filter)
    python filter_specialties.py --country uk --chapters            # Chapter gap analysis
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MERGED_DIR = SCRIPT_DIR / "output" / "merged"

FILTERS = {
    "print": [
        "printer", "printing products", "printing & signage",
        "print company", "print service", "digital print",
        "large format", "litho", "offset print", "commercial print",
        "business print", "print shop"
    ],
    "promo": [
        "promotional product", "promo product", "branded merchandise",
        "corporate gift", "branded gift", "promotional item",
        "promotional merchandise", "branded product"
    ],
    "apparel": [
        "embroid", "uniform", "workwear", "corporate wear",
        "branded clothing", "garment print", "t-shirt print",
        "screen print", "sublimation", "apparel",
        "clothing & accessories", "branded apparel",
        "corporate clothing", "custom clothing", "sportswear"
    ],
    "signage": [
        "sign company", "signage", "sign manufacturer", "sign maker",
        "vehicle wrap", "vehicle graphic", "window graphic", "vinyl wrap",
        "shop front", "illuminated sign"
    ],
}

# Combined filter
FILTERS["print_promo"] = FILTERS["print"] + FILTERS["promo"] + FILTERS["apparel"] + FILTERS["signage"]


def matches_filter(row, filter_type):
    """Check if a row matches the given filter type."""
    if filter_type == "all":
        return True
    keywords = FILTERS.get(filter_type, [])
    combined = (row.get("specialty", "") + " " + row.get("professional_details", "")).lower()
    return any(kw in combined for kw in keywords)


def get_filter_type(row):
    """Return which filter categories a row matches."""
    combined = (row.get("specialty", "") + " " + row.get("professional_details", "")).lower()
    matched = []
    for name, keywords in FILTERS.items():
        if name == "print_promo":
            continue
        if any(kw in combined for kw in keywords):
            matched.append(name)
    return matched


def chapter_analysis(rows):
    """Analyze chapters for gaps in print/promo/apparel/signage."""
    chapters = defaultdict(list)
    for r in rows:
        ch = r.get("chapter", "").strip()
        if ch:
            chapters[ch].append(r)

    print(f"\n{'Chapter':<40} {'Members':<8} {'Print':<8} {'Promo':<8} {'Apparel':<8} {'Signage':<8} {'Gaps'}")
    print("-" * 120)

    for ch_name in sorted(chapters.keys()):
        members = chapters[ch_name]
        has = {}
        for cat in ["print", "promo", "apparel", "signage"]:
            has[cat] = any(matches_filter(m, cat) for m in members)

        gaps = [cat for cat in ["print", "promo", "apparel", "signage"] if not has[cat]]
        gap_str = ", ".join(gaps) if gaps else "none"

        print(
            f"{ch_name:<40} {len(members):<8} "
            f"{'Y' if has['print'] else '-':<8} "
            f"{'Y' if has['promo'] else '-':<8} "
            f"{'Y' if has['apparel'] else '-':<8} "
            f"{'Y' if has['signage'] else '-':<8} "
            f"{gap_str}"
        )

    total_chapters = len(chapters)
    for cat in ["print", "promo", "apparel", "signage"]:
        missing = sum(1 for ch, members in chapters.items() if not any(matches_filter(m, cat) for m in members))
        print(f"\n  {cat}: {missing}/{total_chapters} chapters missing")


def main():
    parser = argparse.ArgumentParser(description="Filter BNI contacts by specialty")
    parser.add_argument("--country", type=str, help="Country code (loads from output/merged/<code>_all.csv)")
    parser.add_argument("--file", type=str, help="Direct CSV file path")
    parser.add_argument("--type", type=str, default="print_promo",
                        choices=list(FILTERS.keys()) + ["all"],
                        help="Filter type (default: print_promo)")
    parser.add_argument("--chapters", action="store_true", help="Chapter gap analysis")
    parser.add_argument("--output", "-o", type=str, help="Output CSV (default: print to stdout)")
    args = parser.parse_args()

    # Load data
    if args.file:
        input_path = Path(args.file)
    elif args.country:
        input_path = MERGED_DIR / f"{args.country}_all.csv"
    else:
        parser.print_help()
        return

    if not input_path.exists():
        print(f"File not found: {input_path}")
        return

    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"[*] Loaded {len(rows)} contacts from {input_path.name}")

    if args.chapters:
        chapter_analysis(rows)
        return

    # Filter
    filtered = [r for r in rows if matches_filter(r, args.type)]
    print(f"[+] {len(filtered)} match filter '{args.type}'")

    if args.output:
        fields = list(rows[0].keys()) if rows else []
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(filtered)
        print(f"[+] Saved to {args.output}")
    else:
        # Print summary
        print(f"\n{'Name':<25} {'Company':<25} {'Chapter':<25} {'Specialty':<30}")
        print("-" * 105)
        for r in filtered[:50]:
            print(
                f"{r.get('name', '?'):<25} "
                f"{r.get('company', ''):<25} "
                f"{r.get('chapter', ''):<25} "
                f"{r.get('specialty', '')[:30]:<30}"
            )
        if len(filtered) > 50:
            print(f"\n... and {len(filtered) - 50} more. Use --output to save all.")


if __name__ == "__main__":
    main()
