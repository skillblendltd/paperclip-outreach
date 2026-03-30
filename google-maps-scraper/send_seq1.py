#!/usr/bin/env python3
"""
Send Sequence 1 (Conversation Starter) to Google Maps prospects.
Non-BNI trust signal: "I run a print and promo shop in Dublin"
Batch: 100/day, 60s delay between sends.
"""

import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = ""  # SET THIS before running
BATCH_SIZE = 100

SUBJECT_A = "quick question about {{COMPANY}}"
SUBJECT_B = "{{FNAME}}, how does your team handle artwork approvals?"

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>I run a print and promo shop in Dublin and I've been chatting with shop owners across Ireland about a common headache.</p>

<p>Quick question: how does your team handle artwork approvals? Most of the shops I've talked to are still doing it over email and WhatsApp, which seems to work until things start slipping through the cracks.</p>

<p>Curious how you manage it.</p>

<p>Prakash<br>
Founder, TaggIQ<br>
<a href="https://taggiq.com">taggiq.com</a></p>
""".strip()


def get_prospects():
    url = f"{API_BASE}/prospects/?campaign_id={CAMPAIGN_ID}&limit=5000"
    resp = urllib.request.urlopen(urllib.request.Request(url))
    data = json.loads(resp.read())
    return data.get("prospects", data if isinstance(data, list) else [])


def send_email(prospect_id, subject, ab_variant):
    payload = {
        "campaign_id": CAMPAIGN_ID,
        "prospect_id": prospect_id,
        "subject": subject,
        "body_html": BODY_HTML,
        "sequence_number": 1,
        "template_name": "gmaps_email_1",
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
    if not CAMPAIGN_ID:
        print("[!] Set CAMPAIGN_ID before running this script.")
        print("    Edit send_seq1.py and add your campaign UUID.")
        return

    prospects = get_prospects()
    # Seq 1: only send to status='new' with 0 emails sent
    to_send = [p for p in prospects
               if p.get("status") == "new"
               and p.get("emails_sent", 0) == 0
               and p.get("send_enabled", True)]
    batch = to_send[:BATCH_SIZE]

    print(f"[*] Campaign: {CAMPAIGN_ID[:8]}...")
    print(f"[*] Total eligible (new, unsent): {len(to_send)}")
    print(f"[*] Sending batch of {len(batch)} today")
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

        time.sleep(60)

    print(f"\n{'=' * 50}")
    print(f" DONE!")
    print(f"   Sent:    {sent}")
    print(f"   Failed:  {failed}")
    print(f"   Remaining: {len(to_send) - len(batch)}")
    print(f"   Run this script again tomorrow for next {BATCH_SIZE}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
