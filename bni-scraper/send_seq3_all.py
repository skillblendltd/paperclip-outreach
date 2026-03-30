#!/usr/bin/env python3
"""Send Email 3 (The Honest Builder) to all TaggIQ campaigns - BNI, Embroidery Global, Promo Global."""

import json
import random
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone as tz

API_BASE = "http://localhost:8002/api"
MIN_DELAY = 30
MAX_DELAY = 60
MIN_GAP_DAYS = 7

CAMPAIGNS = [
    ("64ed1454-18fc-4783-9438-da18143f7312", "TaggIQ BNI Ireland"),
    ("9dc977d3-f793-4051-905c-30c82b76dcd6", "TaggIQ BNI Embroidery Global"),
    ("9cdc1870-476b-4bfe-91ff-9661bd62c662", "TaggIQ BNI Promo Global"),
]

SUBJECT_A = "built this for my own shop, curious what you'd think"
SUBJECT_B = "{{FNAME}}, quick favour to ask"

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>Reaching out again as a fellow BNI member in print and promo. I spent about 20 years building software products (including Toast, the restaurant POS) before starting my own promo shop in Dublin. When I saw how many of us still run on spreadsheets, email threads and manual invoicing, I knew I had to do something about it.</p>

<p>That's how <a href="https://taggiq.com/">TaggIQ</a> came about, a POS platform built specifically for print and promo. Quotes, artwork approvals, orders, invoicing, one place.</p>

<p>I'd genuinely love your feedback. Worth a 15-minute look? As a fellow BNI member, happy to give you 3 months free to try it. No card, no commitment.</p>

<p>If you prefer to explore on your own first, you can sign up for a free trial at <a href="https://taggiq.com/signup">taggiq.com</a>. Just let me know which suppliers you work with and I'll make sure their catalog is loaded for you.</p>

<p>Prakash<br>
Founder, <a href="https://taggiq.com/">TaggIQ</a></p>
""".strip()


def get_prospects(campaign_id):
    url = f"{API_BASE}/prospects/?campaign_id={campaign_id}&limit=1000"
    resp = urllib.request.urlopen(urllib.request.Request(url))
    return json.loads(resp.read()).get("prospects", [])


def send_email(campaign_id, prospect_id, subject, ab_variant):
    payload = {
        "campaign_id": campaign_id,
        "prospect_id": prospect_id,
        "subject": subject,
        "body_html": BODY_HTML,
        "sequence_number": 3,
        "template_name": "bni_email_3",
        "ab_variant": ab_variant,
    }
    req = urllib.request.Request(
        f"{API_BASE}/send/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def main():
    total_sent = total_failed = 0

    for campaign_id, campaign_name in CAMPAIGNS:
        prospects = get_prospects(campaign_id)
        cutoff = datetime.now(tz.utc) - timedelta(days=MIN_GAP_DAYS)
        to_send = []
        skipped_too_soon = 0
        for p in prospects:
            if p.get("emails_sent", 0) == 2 and p.get("status") == "contacted":
                last_emailed = p.get("last_emailed_at", "")
                if last_emailed:
                    try:
                        last_emailed_clean = last_emailed.replace("Z", "+00:00")
                        last_dt = datetime.fromisoformat(last_emailed_clean)
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=tz.utc)
                        if last_dt > cutoff:
                            skipped_too_soon += 1
                            continue
                    except (ValueError, TypeError):
                        pass
                to_send.append(p)

        print(f"\n{'=' * 60}")
        print(f"  {campaign_name}")
        print(f"  Ready for Seq 3: {len(to_send)} (skipped {skipped_too_soon} too soon, <{MIN_GAP_DAYS} days)")
        print(f"{'=' * 60}\n")

        if not to_send:
            print("  Nothing to send!\n")
            continue

        sent = failed = 0

        for i, p in enumerate(to_send):
            pid = p["id"]
            name = p.get("decision_maker_name", "?")
            email = p.get("email", "?")
            biz = p.get("business_name", "?")

            subject = SUBJECT_A if i % 2 == 0 else SUBJECT_B
            variant = "A" if i % 2 == 0 else "B"

            print(f"  [{i+1}/{len(to_send)}] {name} ({biz}) <{email}>...", end=" ", flush=True)

            try:
                result = send_email(campaign_id, pid, subject, variant)
                status = result.get("status", "unknown")
                if status == "sent":
                    sent += 1
                    print("SENT")
                else:
                    failed += 1
                    print(f"{status}: {result.get('error', '')}")
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:200]
                print(f"HTTP {e.code}: {body}")
                failed += 1
                time.sleep(60)
            except Exception as e:
                failed += 1
                print(f"ERROR: {e}")
                time.sleep(60)

            delay = random.randint(MIN_DELAY, MAX_DELAY)
            time.sleep(delay)

        print(f"\n  {campaign_name}: Sent {sent}, Failed {failed}")
        total_sent += sent
        total_failed += failed

    print(f"\n{'=' * 60}")
    print(f"  ALL CAMPAIGNS DONE!")
    print(f"    Total Sent:   {total_sent}")
    print(f"    Total Failed: {total_failed}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
