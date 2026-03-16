#!/usr/bin/env python3
"""Import BNI contacts into the outreach service."""

import csv
import json
import urllib.request

API_URL = "http://localhost:8002/api/import/"
CAMPAIGN_ID = "64ed1454-18fc-4783-9438-da18143f7312"
CSV_FILE = "bni_contacts.csv"

prospects = []
with open(CSV_FILE) as f:
    reader = csv.DictReader(f)
    for row in reader:
        email = (row.get("email") or "").strip()
        if not email or "@" not in email:
            continue

        name = (row.get("name") or "").strip()
        # Split name into first name for decision_maker_name
        first_name = name.split()[0] if name else ""

        prospects.append({
            "business_name": (row.get("company") or name or "").strip(),
            "email": email,
            "decision_maker_name": first_name,
            "decision_maker_title": (row.get("specialty") or "").strip()[:100],
            "city": (row.get("city") or "").strip(),
            "region": (row.get("chapter") or "").strip(),
            "website": (row.get("website") or "").strip(),
            "segment": "promo_distributor",
            "tier": "B",
            "score": 60,
            "notes": f"BNI Member: {name}. Specialty: {row.get('specialty', '')}. Chapter: {row.get('chapter', '')}",
        })

print(f"Importing {len(prospects)} contacts...")

payload = {
    "campaign_id": CAMPAIGN_ID,
    "prospects": prospects,
}

req = urllib.request.Request(
    API_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)

resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print(json.dumps(result, indent=2))
