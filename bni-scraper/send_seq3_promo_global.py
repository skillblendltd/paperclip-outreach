#!/usr/bin/env python3
"""Send Email 3 (The Honest Builder) to BNI promo global contacts who received Seq 2."""

import json
import random
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "9cdc1870-476b-4bfe-91ff-9661bd62c662"
BATCH_SIZE = 600
MIN_DELAY = 30
MAX_DELAY = 60

SUBJECT_A = "built this for my own shop, curious what you'd think"
SUBJECT_B = "{{FNAME}}, quick favour to ask"

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>Reaching out again as a fellow BNI member in print and promo. I spent about 20 years building software products (including Toast, the restaurant POS) before starting my own promo shop in Dublin. When I saw how many of us still run on spreadsheets, email threads and manual invoicing, I knew I had to do something about it.</p>

<p>That's how <a href="https://taggiq.com/">TaggIQ</a> came about, a POS platform built specifically for print and promo. Quotes, artwork approvals, orders, invoicing, one place.</p>

<p>I'd genuinely love your feedback. Worth a 15-minute look? As a fellow BNI member, happy to give you 3 months free to try it. No card, no commitment.</p>

<p>If you prefer to explore on your own first, you can sign up for a free trial at <a href="https://taggiq.com/signup">taggiq.com</a>. Just let me know which suppliers you work with and I'll make sure their catalog is loaded for you.</p>

<p>Prakash</p>
""".strip()


def get_prospects():
    url = f"{API_BASE}/prospects/?campaign_id={CAMPAIGN_ID}&limit=1000"
    resp = urllib.request.urlopen(urllib.request.Request(url))
    return json.loads(resp.read()).get("prospects", [])


def send_email(prospect_id, subject, ab_variant):
    payload = {
        "campaign_id": CAMPAIGN_ID,
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
    prospects = get_prospects()
    # Seq 3: only prospects with exactly 2 emails sent (received Seq 1+2, not replied)
    to_send = [p for p in prospects if p.get("emails_sent", 0) == 2 and p.get("status") == "contacted"]
    batch = to_send[:BATCH_SIZE]

    print(f"[*] Total ready for Seq 3: {len(to_send)}")
    print(f"[*] Sending batch of {len(batch)}")
    print(f"[*] Remaining after this batch: {len(to_send) - len(batch)}\n")

    if not batch:
        print("Nothing to send!")
        return

    sent = failed = 0

    for i, p in enumerate(batch):
        pid = p["id"]
        name = p.get("decision_maker_name", "?")
        email = p.get("email", "?")
        biz = p.get("business_name", "?")

        subject = SUBJECT_A if i % 2 == 0 else SUBJECT_B
        variant = "A" if i % 2 == 0 else "B"

        print(f"  [{i+1}/{len(batch)}] {name} ({biz}) <{email}>...", end=" ", flush=True)

        try:
            result = send_email(pid, subject, variant)
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

    print(f"\n{'=' * 50}")
    print(f" DONE!")
    print(f"   Sent:    {sent}")
    print(f"   Failed:  {failed}")
    print(f"   Remaining: {len(to_send) - len(batch)}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
