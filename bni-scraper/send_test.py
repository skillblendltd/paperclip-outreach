#!/usr/bin/env python3
"""Send test Email 1 to prakash@taggiq.com via the outreach API."""

import json
import urllib.request

API_URL = "http://localhost:8002/api/send/"
CAMPAIGN_ID = "64ed1454-18fc-4783-9438-da18143f7312"
PROSPECT_ID = "db366d6a-3d40-40dd-9fb8-d64e7b0cf92d"

body_html = """
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

payload = {
    "campaign_id": CAMPAIGN_ID,
    "prospect_id": PROSPECT_ID,
    "subject": "Fellow BNI member in print and promo",
    "body_html": body_html,
    "sequence_number": 1,
    "template_name": "bni_email_1"
}

req = urllib.request.Request(
    API_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print(json.dumps(result, indent=2))
