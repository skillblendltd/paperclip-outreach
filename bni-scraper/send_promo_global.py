#!/usr/bin/env python3
"""Send Email 1 to BNI promo global contacts (100/day batch)."""

import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "9cdc1870-476b-4bfe-91ff-9661bd62c662"
BATCH_SIZE = 100

SUBJECT_A = "quick question about {{COMPANY}}"
SUBJECT_B = "{{FNAME}}, how do you handle artwork approvals?"

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>Spotted you on BNI Connect, looks like we're both in the print and promo world.</p>

<p>Quick question: how does your team handle artwork approvals? I've talked to a bunch of BNI members recently and it's wild how many are still chasing approvals over email and WhatsApp.</p>

<p>Curious if you've found something that works or if it's still a pain.</p>

<p>Prakash<br>
Founder, <a href="https://taggiq.com/">TaggIQ</a></p>
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
        "sequence_number": 1,
        "template_name": "bni_email_1",
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
    to_send = [p for p in prospects if p.get("emails_sent", 0) == 0]
    batch = to_send[:BATCH_SIZE]

    print(f"[*] Total unsent: {len(to_send)}")
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
    print(f"   Run this script again tomorrow for next 100")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
