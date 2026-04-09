#!/bin/bash
# UK BNI Scrape - Complete Pipeline
# Applies Canada learnings: merge existing data first, then re-scrape with --existing to fill gaps
#
# What we have:
#   raw/uk_20260402.csv        - 1,250 profiles (858 emails) - first batch
#   merged/uk_all_20260403.csv - 6,060 names, profiles 1250+ visited (3,308 emails)
#
# Strategy:
#   1. Merge both files into one comprehensive existing file
#   2. Re-scrape UK (country-level, no regions) with --existing to fill gaps
#   3. Only profiles without email get re-visited = ~1,900 profiles instead of 6,000+

cd "$(dirname "$0")"

MERGED_EXISTING="output/merged/uk_existing_combined.csv"
FINAL_OUTPUT="output/merged/uk_all_final.csv"

echo "=== Step 1: Merge existing UK data ==="
python3 merge_uk_existing.py
echo ""

echo "=== Step 2: Re-scrape UK with --existing to fill gaps ==="
echo "This will only visit profiles that don't have an email yet."
echo "Output: output/raw/uk_$(date +%Y%m%d).csv"
echo ""

python3 scrape_bni.py \
    --config configs/uk.json \
    --existing "$MERGED_EXISTING"

echo ""
echo "=== Step 3: Move final output to merged ==="
LATEST=$(ls -t output/raw/uk_*.csv 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    cp "$LATEST" "$FINAL_OUTPUT"
    echo "Final file: $FINAL_OUTPUT"

    # Quick stats
    python3 -c "
import csv
with open('$FINAL_OUTPUT') as f:
    rows = list(csv.DictReader(f))
total = len(rows)
emails = sum(1 for r in rows if r.get('email','').strip())
phones = sum(1 for r in rows if r.get('phone','').strip())
print(f'Total: {total} contacts')
print(f'Emails: {emails} ({100*emails//total}%)')
print(f'Phones: {phones} ({100*phones//total}%)')
"
else
    echo "No output file found!"
fi
