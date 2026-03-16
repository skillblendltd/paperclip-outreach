#!/usr/bin/env python3
"""
Import Fully Promoted Ireland franchise prospects from Synuma CSV export
into the Paperclip Outreach campaign system.

Data source: synuma-lead-list.csv (exported from Synuma CRM with emails)

Usage:
    1. Create campaign in Django admin at http://localhost:8002/admin/
       - Name: "FP Ireland Franchise Recruitment"
       - Product: "fullypromoted"
       - From name: "Prakash Inani"
       - From email: <SES-verified email>
       - Reply-to: <your reply email>
       - Max emails/day: 20
       - Max emails/prospect: 5
       - Follow-up days: 5
       - Sending enabled: OFF (turn on when ready)

    2. Set CAMPAIGN_ID below to the UUID from admin.

    3. Run: python3 import_prospects.py

    4. Verify in admin, then run send_campaign.py
"""

import csv
import json
import urllib.request
from datetime import datetime

API_URL = "http://localhost:8002/api/import/"
CAMPAIGN_ID = "50eecf8f-c4a0-4a2d-9335-26d56870101e"
CSV_FILE = "synuma-lead-list.csv"

# Skip these statuses
SKIP_STATUSES = {"Do Not Contact (Lead Lost)"}

# Skip own email
OWN_EMAILS = {"prakash.inani@gmail.com"}

# Map stages to tiers based on engagement depth
STAGE_TIER_MAP = {
    "Discovery Day": "A",
    "Application/FDD": "A",
    "Tour/Webinar": "B",
    "Passed Leads": "B",
    "Inquiry": "C",
}

# Score based on how far they progressed
STAGE_SCORE_MAP = {
    "Discovery Day": 90,
    "Application/FDD": 85,
    "Tour/Webinar": 70,
    "Passed Leads": 65,
    "Inquiry": 50,
}


def parse_year(date_str):
    """Extract year from various date formats."""
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    for fmt in ["%b %d, %Y", "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return str(datetime.strptime(date_str, fmt).year)
        except ValueError:
            continue
    return ""


def parse_name(name_str):
    """Parse 'Last, First' into (first_name, last_name, full_name)."""
    if not name_str:
        return "", "", ""
    name = str(name_str).strip()
    if "," in name:
        parts = name.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip()
        return first, last, f"{first} {last}"
    parts = name.split()
    if len(parts) >= 2:
        return parts[0], parts[-1], name
    return name, "", name


def main():
    if not CAMPAIGN_ID:
        print("=" * 60)
        print("ERROR: CAMPAIGN_ID not set!")
        print()
        print("Steps:")
        print("  1. Go to http://localhost:8002/admin/campaigns/campaign/add/")
        print('  2. Create: "FP Ireland Franchise Recruitment"')
        print('     - Product: fullypromoted')
        print('     - From name: Prakash Inani')
        print('     - From email: <your SES-verified email>')
        print('     - Max emails/day: 20')
        print('     - Max emails/prospect: 5')
        print("     - Sending enabled: OFF")
        print("  3. Copy the UUID and set CAMPAIGN_ID in this script")
        print("=" * 60)
        return

    prospects = []
    skipped_dnc = 0
    skipped_dupe = 0
    skipped_no_email = 0
    skipped_own = 0
    seen_emails = set()

    with open(CSV_FILE, encoding="utf-8-sig") as f:
        # Skip the "Table 1" header line if present
        first_line = f.readline().strip()
        if first_line != "Table 1":
            f.seek(0)

        reader = csv.DictReader(f)

        for row in reader:
            name_raw = (row.get("Name") or "").strip()
            if not name_raw:
                continue

            status = (row.get("Status") or "").strip()
            if status in SKIP_STATUSES:
                skipped_dnc += 1
                continue

            email = (row.get("Email Address") or "").strip()
            if not email or "@" not in email:
                skipped_no_email += 1
                continue

            # Skip own email
            if email.lower() in OWN_EMAILS:
                skipped_own += 1
                continue

            # De-duplicate by email
            email_key = email.lower()
            if email_key in seen_emails:
                skipped_dupe += 1
                continue
            seen_emails.add(email_key)

            stage = (row.get("Current Stage") or "").strip()
            source = (row.get("Source") or "").strip()
            initial_date = (row.get("Initial Contact Date") or "").strip()
            last_task = (row.get("Last Task Complete") or "").strip()
            city = (row.get("City") or "").strip()
            investment_tf = (row.get("Investment Timeframe") or "").strip()
            how_heard = (row.get("How did you hear about us?") or "").strip()

            first_name, last_name, full_name = parse_name(name_raw)

            # Tier and score
            tier = STAGE_TIER_MAP.get(stage, "C")
            score = STAGE_SCORE_MAP.get(stage, 40)

            # Boost score for recent enquiries
            year = parse_year(initial_date)
            if year:
                year_int = int(year)
                if year_int >= 2024:
                    score += 10
                elif year_int >= 2022:
                    score += 5

            enquiry_year = year or "unknown"

            # Clean city
            clean_city = city if city.lower() not in ("tbd", "na", "n/a", "") else ""

            # Build notes
            notes_parts = [
                f"Source: {source}" if source else "",
                f"Stage: {stage}" if stage else "",
                f"Initial contact: {initial_date}" if initial_date else "",
                f"Last task: {last_task}" if last_task else "",
                f"Investment timeframe: {investment_tf}" if investment_tf else "",
                f"How heard: {how_heard}" if how_heard else "",
                f"Enquiry year: {enquiry_year}",
            ]
            notes = ". ".join(p for p in notes_parts if p)

            prospects.append(
                {
                    "business_name": full_name,
                    "email": email,
                    "decision_maker_name": first_name,
                    "decision_maker_title": "",
                    "city": clean_city,
                    "region": "Ireland",
                    "website": "",
                    "segment": "",
                    "tier": tier,
                    "score": score,
                    "notes": notes,
                    "business_type": "franchise_prospect",
                    "pain_signals": f"Enquired {enquiry_year}. Stage reached: {stage}. Source: {source}",
                }
            )

    # Summary
    print(f"{'=' * 55}")
    print(f"  FP Ireland Franchise Recruitment — Import")
    print(f"{'=' * 55}")
    print(f"  Contactable prospects:  {len(prospects)}")
    print(f"  Skipped DNC:            {skipped_dnc}")
    print(f"  Skipped duplicates:     {skipped_dupe}")
    print(f"  Skipped no email:       {skipped_no_email}")
    print(f"  Skipped own email:      {skipped_own}")
    print(f"{'=' * 55}")
    print(f"  Tier A (Discovery/Application):  {sum(1 for p in prospects if p['tier'] == 'A')}")
    print(f"  Tier B (Tour/Webinar/Passed):    {sum(1 for p in prospects if p['tier'] == 'B')}")
    print(f"  Tier C (Inquiry only):           {sum(1 for p in prospects if p['tier'] == 'C')}")
    print(f"{'=' * 55}")
    print()

    # Import
    payload = {
        "campaign_id": CAMPAIGN_ID,
        "prospects": prospects,
    }

    print(f"Importing {len(prospects)} prospects...")
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        print(json.dumps(result, indent=2))
        print()
        print("Done! Next steps:")
        print("  1. Review prospects in admin: http://localhost:8002/admin/campaigns/prospect/")
        print("  2. Enable sending in admin when ready")
        print("  3. Dry run:  python3 send_campaign.py --seq 1 --dry-run")
        print("  4. Send:     python3 send_campaign.py --seq 1 --tier A")
    except Exception as e:
        print(f"\nERROR: {e}")
        print("Is the outreach server running on http://localhost:8002 ?")


if __name__ == "__main__":
    main()
