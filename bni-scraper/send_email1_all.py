#!/usr/bin/env python3
"""Send Email 1 (The Opener) to all BNI contacts via the outreach API."""

import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "64ed1454-18fc-4783-9438-da18143f7312"

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
    """Fetch all eligible prospects from the campaign."""
    url = f"{API_BASE}/prospects/?campaign_id={CAMPAIGN_ID}&limit=200"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    return data.get("prospects", [])


def send_email(prospect_id, subject, ab_variant):
    """Send Email 1 to a single prospect."""
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
    print(f"[*] Found {len(prospects)} eligible prospects\n")

    # Filter only those who haven't been emailed yet
    to_send = [p for p in prospects if p.get("emails_sent", 0) == 0]
    print(f"[*] {len(to_send)} prospects haven't received Email 1 yet\n")

    if not to_send:
        print("Nothing to send!")
        return

    sent = 0
    failed = 0
    blocked = 0

    for i, prospect in enumerate(to_send):
        pid = prospect["id"]
        name = prospect.get("decision_maker_name", "?")
        email = prospect.get("email", "?")
        biz = prospect.get("business_name", "?")

        # A/B test: alternate subject lines
        if i % 2 == 0:
            subject = SUBJECT_A
            variant = "A"
        else:
            subject = SUBJECT_B
            variant = "B"

        print(f"  [{i+1}/{len(to_send)}] {name} ({biz}) <{email}>...", end=" ", flush=True)

        try:
            result = send_email(pid, subject, variant)
            status = result.get("status", "unknown")

            if status == "sent":
                sent += 1
                print("SENT")
            elif status == "blocked":
                blocked += 1
                print(f"BLOCKED: {result.get('error', '')}")
            elif status == "rate_limited":
                blocked += 1
                print(f"RATE LIMITED: {result.get('error', '')}")
                print("  [*] Waiting 60 seconds...")
                time.sleep(60)
            else:
                failed += 1
                print(f"{status}: {result.get('error', '')}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            print(f"HTTP {e.code}: {body}")
            failed += 1
            if e.code == 429 or "rate" in body.lower():
                print("  [*] Rate limited. Waiting 60 seconds...")
                time.sleep(60)
            else:
                print("  [*] Waiting 10 seconds before retry...")
                time.sleep(10)
        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")
            time.sleep(5)

        # 5 second delay between sends to avoid SES throttling
        time.sleep(5)

    print(f"\n{'=' * 50}")
    print(f" DONE!")
    print(f"   Sent:    {sent}")
    print(f"   Blocked: {blocked}")
    print(f"   Failed:  {failed}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
