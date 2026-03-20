#!/usr/bin/env python3
"""Send Email 2 (Shared Pain) to BNI promo global contacts who received Seq 1 7+ days ago."""

import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "9cdc1870-476b-4bfe-91ff-9661bd62c662"
BATCH_SIZE = 100

SUBJECT_A = "the artwork approval problem"
SUBJECT_B = "{{FNAME}}, thought you'd find this interesting"

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>Thought you might find this interesting. I asked about 20 BNI members in print and promo how they handle artwork approvals and order tracking. Almost everyone said some version of "email back and forth until someone finally says yes."</p>

<p>I actually built a tool to fix this for my own shop in Dublin. It's called <a href="https://taggiq.com/">TaggIQ</a> and it connects quotes, approvals, orders and invoicing in one place. I'm also putting together a small group of BNI promo owners to share best practices on workflow.</p>

<p>Happy to share what I learned if you're dealing with the same thing.</p>

<p>Either way, no worries.</p>

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
        "sequence_number": 2,
        "template_name": "bni_email_2",
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
    # Seq 2: only prospects with exactly 1 email sent (received Seq 1, not replied)
    to_send = [p for p in prospects if p.get("emails_sent", 0) == 1 and p.get("status") == "contacted"]
    batch = to_send[:BATCH_SIZE]

    print(f"[*] Total ready for Seq 2: {len(to_send)}")
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

        time.sleep(60)

    print(f"\n{'=' * 50}")
    print(f" DONE!")
    print(f"   Sent:    {sent}")
    print(f"   Failed:  {failed}")
    print(f"   Remaining: {len(to_send) - len(batch)}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
