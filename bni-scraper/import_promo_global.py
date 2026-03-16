#!/usr/bin/env python3
"""Import BNI promo global contacts, skipping duplicates from previous campaigns."""

import csv
import json
import urllib.request

API_URL = "http://localhost:8002/api/import/"
CAMPAIGN_ID = "9cdc1870-476b-4bfe-91ff-9661bd62c662"
CSV_FILE = "bni_promo_global.csv"

# Get existing emails from previous campaigns
existing_emails = set()
for cid in ["64ed1454-18fc-4783-9438-da18143f7312", "9dc977d3-f793-4051-905c-30c82b76dcd6"]:
    resp = urllib.request.urlopen(f"http://localhost:8002/api/prospects/?campaign_id={cid}&limit=500")
    data = json.loads(resp.read())
    for p in data.get("prospects", []):
        existing_emails.add(p["email"].lower())

# Also check suppression list
resp = urllib.request.urlopen("http://localhost:8002/api/prospects/?campaign_id=" + CAMPAIGN_ID + "&limit=1")

print(f"Existing emails to skip: {len(existing_emails)}")

prospects = []
skipped = 0
with open(CSV_FILE) as f:
    reader = csv.DictReader(f)
    for row in reader:
        email = (row.get("email") or "").strip()
        if not email or "@" not in email:
            continue
        if email.lower() in existing_emails:
            skipped += 1
            continue

        name = (row.get("name") or "").strip()
        first_name = name.split()[0] if name else ""

        prospects.append({
            "business_name": (row.get("company") or name or "").strip(),
            "email": email,
            "decision_maker_name": first_name,
            "decision_maker_title": (row.get("specialty") or "").strip()[:100],
            "city": (row.get("city") or "").strip(),
            "region": (row.get("country") or row.get("chapter") or "").strip(),
            "website": (row.get("website") or "").strip(),
            "segment": "promo_distributor",
            "tier": "B",
            "score": 60,
            "notes": f"BNI Member: {name}. Specialty: {row.get('specialty', '')}. Chapter: {row.get('chapter', '')}",
        })

print(f"Skipped (already in other campaigns): {skipped}")
print(f"Importing {len(prospects)} new contacts...")

# Import in batches of 200
for i in range(0, len(prospects), 200):
    batch = prospects[i:i+200]
    payload = {"campaign_id": CAMPAIGN_ID, "prospects": batch}
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"  Batch {i//200 + 1}: created={result['created']}, updated={result['updated']}, skipped={result['skipped']}")

print(f"\nDone! Total imported: {len(prospects)}")
