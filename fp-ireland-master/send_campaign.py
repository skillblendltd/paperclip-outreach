#!/usr/bin/env python3
"""
Send Fully Promoted Ireland franchise recruitment emails.

5-email re-engagement sequence:
  --seq 1  The Re-Engagement (Day 0)
  --seq 2  Why This, Why Now (Day 5)
  --seq 3  Social Proof & Success Stories (Day 12)
  --seq 4  Handle Objections & Create Urgency (Day 20)
  --seq 5  The Breakup Email (Day 28)

Usage:
    python3 send_campaign.py --seq 1              # Send Email 1 to all unsent
    python3 send_campaign.py --seq 1 --dry-run    # Preview without sending
    python3 send_campaign.py --seq 1 --tier A     # Only Tier A prospects
    python3 send_campaign.py --status             # Show campaign stats
    python3 send_campaign.py --seq 2 --max 50     # Send Email 2, max 50
"""

import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "50eecf8f-c4a0-4a2d-9335-26d56870101e"


# ---------------------------------------------------------------------------
# Email templates (HTML versions)
# ---------------------------------------------------------------------------

EMAILS = {
    1: {
        "template_name": "fp_reengagement",
        "subjects": {
            "A": "{{FNAME}}, are you still open to business opportunities?",
            "B": "You enquired about Fully Promoted -things have changed, {{FNAME}}",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>You enquired some time back about the Fully Promoted franchise opportunity in Ireland, and I wanted to reach out personally to see if you're still open to exploring business opportunities.</p>

<p>A lot has happened since {{YEAR}}.</p>

<p>Fully Promoted is now the world's largest promotional products franchise -ranked <strong>#1 in our category by Entrepreneur Magazine for 25 years running</strong>, with over 275 locations across 10 countries and still growing.</p>

<p>The reason I'm reaching out is that we're now bringing Fully Promoted to Ireland, and I'm looking for the right franchise partners to help make that happen.</p>

<p>I'm Prakash, the Master Franchisee for Ireland. Would be great to have a quick chat and fill you in on where things are at. Happy to send over the franchise brochure too if you'd like a read first.</p>

<p>Either way, just hit reply and let me know. Would love to hear from you.</p>

<p>Best regards,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
    2: {
        "template_name": "fp_business_case",
        "subjects": {
            "A": "Why promotional products is a recession-resistant business",
            "B": "The franchise opportunity I wish I'd seen 10 years ago",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>I sent you a note last week about Fully Promoted Ireland and I wanted to follow up with a bit more context, because the numbers really do speak for themselves.</p>

<p>The promotional products industry globally is worth over $26 billion -and it's growing. Every business in Ireland needs branded merchandise: uniforms, workwear, corporate gifts, trade show materials, marketing collateral. It's not a trend. It's a permanent, recurring business need.</p>

<p>That's what makes Fully Promoted so compelling as a franchise. Your clients don't buy once and disappear. Staff turn over, companies rebrand, events happen every quarter. You build relationships and they keep coming back, year after year.</p>

<p>Here's what you get with a Fully Promoted franchise:</p>
<ul>
<li>A turnkey operation: all equipment, software, and store setup included</li>
<li>Intensive 4-week training programme (no prior industry experience needed)</li>
<li>Established supplier relationships from day one</li>
<li>Ongoing support from a global network of 275+ franchisees</li>
<li>A brand that's been ranked #1 in its category for 25 consecutive years</li>
</ul>

<p>Ireland is a brand-new market for Fully Promoted, which means the franchise partners who come in now will have first pick of territories.</p>

<p>Would you be open to a 15-minute call this week? I can walk you through the full opportunity pack. Happy to work around your schedule.</p>

<p>Best regards,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
    3: {
        "template_name": "fp_social_proof",
        "subjects": {
            "A": "From corporate job to million-dollar franchise owner",
            "B": "How Fully Promoted franchisees are building real businesses",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>I've been reaching out about the Fully Promoted franchise opportunity in Ireland and I thought you might find this interesting.</p>

<p>One of the things that convinced me to take on the Ireland master franchise was the success stories from existing owners around the world.</p>

<p>Michelle Bottino left her corporate career in 2018 to open a Fully Promoted store in Illinois. Within a few years, she'd grown it into a million-dollar operation. A franchisee in Ohio saw 72% sales growth in a single year. Others have come from completely different backgrounds -retail, hospitality, corporate -and built thriving businesses because the system does the heavy lifting.</p>

<p>That's the beauty of this model. You don't need to be an expert in promotional products. Fully Promoted gives you the training, the suppliers, the technology, and the brand. Your job is building relationships with local businesses.</p>

<p>I'm currently putting together the founding group of franchise partners for Ireland's launch. This is a ground-floor opportunity -the kind that doesn't come around often.</p>

<p>I'd genuinely love to include you in that conversation. Would a quick Zoom call work for you this week or next?</p>

<p>Best regards,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
    4: {
        "template_name": "fp_objection_handler",
        "subjects": {
            "A": "Quick question, {{FNAME}}",
            "B": "{{FNAME}}, I have a question for you",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>I've reached out a couple of times about Fully Promoted Ireland and I understand you're busy, so I'll be direct.</p>

<p>When people consider a franchise, the three things they usually ask are:</p>

<p><strong>1. "Do I need experience?"</strong> -No. Fully Promoted provides 4 weeks of intensive training and ongoing support. Many of our most successful franchisees came from completely unrelated industries.</p>

<p><strong>2. "What's the investment?"</strong> -The franchise fee is very competitive for a brand of this calibre, and the total investment includes a fully fitted-out, turnkey store ready to trade from day one.</p>

<p><strong>3. "Is there really a market for this in Ireland?"</strong> -Every business in Ireland needs branded products. Uniforms, corporate gifts, event merchandise, marketing materials. It's a €500M+ market and there's currently no dominant branded franchise serving it.</p>

<p>I'm allocating territories across Ireland right now -Dublin, Cork, Galway, Limerick, Waterford and beyond. Once they're assigned, they're gone.</p>

<p>If you've even a small interest, a 15-minute call will give you everything you need to make an informed decision. No hard sell, no obligation.</p>

<p>Just reply <strong>"interested"</strong> and I'll set it up.</p>

<p>Best regards,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
    5: {
        "template_name": "fp_breakup",
        "subjects": {
            "A": "Closing your file, {{FNAME}}",
            "B": "Closing your file, {{FNAME}}",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>I've reached out a few times about the Fully Promoted franchise opportunity in Ireland and I haven't heard back, so I'm going to assume the timing isn't right for you.</p>

<p>Completely understand -not every opportunity is the right fit at the right time.</p>

<p>I'm going to close your enquiry file on my end, but if things change down the road and you'd like to explore this, my door is always open. Just reply to this email anytime.</p>

<p>For what it's worth, Fully Promoted is celebrating 25 years in business this year, and we're just getting started in Ireland. The opportunity will only grow from here.</p>

<p>I wish you all the best, {{FNAME}}.</p>

<p>Warm regards,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
}

# No tier-specific additions - same email for all tiers
TIER_A_ADDITION = ""


def ab_variant(prospect_id):
    """Deterministic A/B assignment via MD5 hash."""
    h = hashlib.md5(str(prospect_id).encode()).hexdigest()
    return "A" if int(h, 16) % 2 == 0 else "B"


def get_prospects(tier=None, status=None):
    """Fetch eligible prospects from the campaign."""
    params = f"campaign_id={CAMPAIGN_ID}&has_email=true&limit=500"
    if tier:
        params += f"&tier={tier}"
    if status:
        params += f"&status={status}"
    url = f"{API_BASE}/prospects/?{params}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    return data.get("prospects", [])


def get_status():
    """Get campaign status."""
    url = f"{API_BASE}/status/?campaign_id={CAMPAIGN_ID}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def extract_year(prospect):
    """Extract enquiry year from prospect notes/pain_signals."""
    for field in ["pain_signals", "notes"]:
        text = prospect.get(field, "")
        # pain_signals format: "Enquired 2021. Stage reached: ..."
        if "Enquired " in text:
            for part in text.split("."):
                part = part.strip()
                if part.startswith("Enquired "):
                    year = part.replace("Enquired ", "").strip()
                    if year.isdigit() and len(year) == 4:
                        return year
        # notes format: "... Enquiry year: 2021"
        if "Enquiry year:" in text:
            for part in text.split("."):
                if "Enquiry year:" in part:
                    year = part.split(":")[-1].strip()
                    if year.isdigit() and len(year) == 4:
                        return year
    return "a while back"


def send_email(prospect_id, subject, body_html, seq, variant):
    """Send a single email via the outreach API."""
    payload = {
        "campaign_id": CAMPAIGN_ID,
        "prospect_id": prospect_id,
        "subject": subject,
        "body_html": body_html,
        "sequence_number": seq,
        "template_name": EMAILS[seq]["template_name"],
        "ab_variant": variant,
    }
    req = urllib.request.Request(
        f"{API_BASE}/send/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def show_status():
    """Display campaign status."""
    try:
        status = get_status()
    except Exception as e:
        print(f"\nERROR: Could not reach API -{e}")
        print("Is the outreach server running on http://localhost:8002 ?")
        return

    print(f"\n{'=' * 55}")
    print(f"  Campaign: {status['campaign']}")
    print(f"  Sending:  {'ON' if status['sending_enabled'] else 'OFF'}")
    print(f"  From:     {status['from_name']} <{status['from_email']}>")
    print(f"{'=' * 55}")
    print(f"  Total prospects:     {status['total_prospects']}")
    print(f"  With email:          {status['prospects_with_email']}")
    print(f"  Sent today:          {status['sent_today']}/{status['max_emails_per_day']}")
    print(f"  Remaining today:     {status['remaining_today']}")
    print(f"  Last sent:           {status.get('last_sent_at', 'Never')}")
    print(f"  A/B stats:           A={status['ab_stats']['A']}  B={status['ab_stats']['B']}")
    print(f"{'=' * 55}\n")


def main():
    parser = argparse.ArgumentParser(description="Send FP Ireland franchise recruitment emails")
    parser.add_argument("--seq", type=int, choices=[1, 2, 3, 4, 5], help="Sequence number to send")
    parser.add_argument("--tier", type=str, choices=["A", "B", "C"], help="Only send to specific tier")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--status", action="store_true", help="Show campaign status")
    parser.add_argument("--max", type=int, default=100, help="Max emails per run (default 100)")
    args = parser.parse_args()

    if not CAMPAIGN_ID:
        print("=" * 60)
        print("ERROR: CAMPAIGN_ID not set!")
        print()
        print("Set CAMPAIGN_ID in this script to match the UUID")
        print("from http://localhost:8002/admin/campaigns/campaign/")
        print("=" * 60)
        return

    if args.status:
        show_status()
        return

    if not args.seq:
        print("Usage:")
        print("  python3 send_campaign.py --seq 1              # Send Email 1")
        print("  python3 send_campaign.py --seq 1 --dry-run    # Preview")
        print("  python3 send_campaign.py --seq 1 --tier A     # Tier A only")
        print("  python3 send_campaign.py --status             # Stats")
        return

    seq = args.seq
    email_config = EMAILS[seq]

    # Fetch prospects based on sequence
    # seq 1: prospects with emails_sent == 0
    # seq 2+: prospects with status == 'contacted' and emails_sent == seq - 1
    if seq == 1:
        prospects = get_prospects(tier=args.tier)
        to_send = [p for p in prospects if p.get("emails_sent", 0) == 0]
    else:
        prospects = get_prospects(tier=args.tier, status="contacted")
        to_send = [p for p in prospects if p.get("emails_sent", 0) == seq - 1]

    # Sort: Tier A first, then B, then C; within each tier, highest score first
    tier_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    to_send.sort(key=lambda p: (tier_order.get(p.get("tier", "C"), 3), -p.get("score", 0)))

    # Apply max limit
    to_send = to_send[: args.max]

    seq_names = {
        1: "The Re-Engagement",
        2: "Why This, Why Now",
        3: "Social Proof & Success Stories",
        4: "Handle Objections & Urgency",
        5: "The Breakup Email",
    }

    print(f"\n[*] Email {seq}: {seq_names[seq]}")
    print(f"[*] Template: {email_config['template_name']}")
    print(f"[*] Found {len(to_send)} prospects to send")
    if args.tier:
        print(f"[*] Filtered to Tier {args.tier}")
    if args.dry_run:
        print("[*] DRY RUN -no emails will be sent\n")
    print()

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
        tier = prospect.get("tier", "?")
        score = prospect.get("score", 0)

        # Determine A/B variant
        variant = ab_variant(pid)
        subject = email_config["subjects"][variant]

        # Build body
        body = email_config["body_html"]

        # Tier A personalisation for Email 1
        if seq == 1 and tier == "A":
            body = body.replace(
                "<p>Are you still interested?",
                TIER_A_ADDITION + "\n\n<p>Are you still interested?",
            )

        # Replace {{YEAR}} with actual enquiry year
        year = extract_year(prospect)
        body = body.replace("{{YEAR}}", year)
        subject = subject.replace("{{YEAR}}", year)

        print(
            f"  [{i + 1}/{len(to_send)}] [{tier}/{score}] {name} <{email}> "
            f"[{variant}]...",
            end=" ",
            flush=True,
        )

        if args.dry_run:
            print(f"WOULD SEND: \"{subject}\"")
            sent += 1
            continue

        try:
            result = send_email(pid, subject, body, seq, variant)
            result_status = result.get("status", "unknown")

            if result_status == "sent":
                sent += 1
                print("SENT")
            elif result_status == "blocked":
                blocked += 1
                print(f"BLOCKED: {result.get('error', '')}")
            elif result_status == "rate_limited":
                blocked += 1
                wait = result.get("wait_seconds", 60)
                print(f"RATE LIMITED -waiting {wait}s...")
                time.sleep(max(wait, 60))
            else:
                failed += 1
                print(f"{result_status}: {result.get('error', '')}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
            print(f"HTTP {e.code}: {err_body}")
            failed += 1
            if e.code == 429 or "rate" in err_body.lower():
                print("  [*] Rate limited. Waiting 60s...")
                time.sleep(60)
            else:
                time.sleep(10)
        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")
            time.sleep(5)

        # Gap between sends
        if not args.dry_run:
            time.sleep(5)

    print(f"\n{'=' * 50}")
    prefix = "DRY RUN " if args.dry_run else ""
    print(f" {prefix}DONE -Email {seq}: {seq_names[seq]}")
    print(f"   Sent:    {sent}")
    print(f"   Blocked: {blocked}")
    print(f"   Failed:  {failed}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
