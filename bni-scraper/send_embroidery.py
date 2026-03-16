#!/usr/bin/env python3
"""Send Email 1 to all BNI embroidery contacts."""

import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "9dc977d3-f793-4051-905c-30c82b76dcd6"

SUBJECT_A = "Fellow BNI member in print and promo"
SUBJECT_B = "{{FNAME}}, quick one from a fellow BNI member"

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>Hope you're well. I came across your profile on BNI Connect and noticed we're both in the print and promo space, so I thought I'd say hello.</p>

<p>I run a print and promo shop in Dublin, and one thing that always drove me mad was having everything in different places. Quotes in one tool, artwork approvals over email, purchase orders somewhere else, and then re-entering everything into Xero at the end. The same order getting typed four different times.</p>

<p>In the end, I built something to solve it for our own shop. It's called <a href="https://taggiq.com/">TaggIQ</a> and it connects the whole journey from quote to invoice in one place, built specifically for how print and promo businesses actually work.</p>

<p>I'd be really interested to hear how you're managing this at {{COMPANY}}. Always great to learn how other BNI members in the industry handle their workflow.</p>

<p>If you're curious, I'd be happy to share what we built. No pressure at all.</p>

<p>Best regards,<br>
Prakash Inani<br>
Founder, <a href="https://taggiq.com/">TaggIQ</a><br>
Kingswood Business Park, Dublin<br>
<a href="https://taggiq.com/">https://taggiq.com</a></p>
""".strip()


def get_prospects():
    url = f"{API_BASE}/prospects/?campaign_id={CAMPAIGN_ID}&limit=200"
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
    print(f"[*] {len(to_send)} contacts to email\n")

    if not to_send:
        print("Nothing to send!")
        return

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
            time.sleep(10)
        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")
            time.sleep(5)

        time.sleep(5)

    print(f"\n{'=' * 50}")
    print(f" DONE!")
    print(f"   Sent:    {sent}")
    print(f"   Failed:  {failed}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
