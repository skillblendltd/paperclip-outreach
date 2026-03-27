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
            "A": "Fully Promoted Ireland - quick update, {{FNAME}}",
            "B": "{{FNAME}}, remember your franchise enquiry?",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>You enquired about the Fully Promoted franchise in Ireland back in {{YEAR}}. At the time, we weren't quite ready to launch here.</p>

<p>Now we are.</p>

<p>Fully Promoted is the world's largest promotional products franchise - #1 in our category for 25 years running, with over 300 locations worldwide. And we're now looking for franchise partners across Ireland.</p>

<p>I'm Prakash, the Master Franchisee for Ireland. Would love to have a quick chat and fill you in, or send over the franchise brochure if you'd prefer a read first.</p>

<p>Just hit reply either way. Would be great to hear from you.</p>

<p>Cheers,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Unit A20, Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
    2: {
        "template_name": "fp_business_case",
        "subjects": {
            "A": "Quick thought on the Irish market, {{FNAME}}",
            "B": "Why I picked Fully Promoted for Ireland",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>Prakash here from Fully Promoted Ireland. You enquired about a franchise with us a while back, so I wanted to reach out.</p>

<p>I'm the Master Franchisee for Ireland and we're now actively looking for franchise partners. The thing I love about this model is that every business needs branded products, uniforms, and marketing materials, and they come back for more every quarter. It's a proper recurring revenue business.</p>

<p>Would be great to have a quick chat if you're open to it. Here's a link to grab a time that suits you: <a href="https://calendar.app.google/yFLeFoyP3XscHsBs8">https://calendar.app.google/yFLeFoyP3XscHsBs8</a></p>

<p>Cheers,<br>
Prakash Inani<br>
Master Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Unit A20, Kingswood Business Park, Dublin<br>
<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>
""".strip(),
    },
    3: {
        "template_name": "fp_social_proof",
        "subjects": {
            "A": "How a first-timer built a million-dollar franchise",
            "B": "Something I thought you'd find interesting, {{FNAME}}",
        },
        "body_html": """
<p>Hi {{FNAME}},</p>

<p>Thought you might find this relevant.</p>

<p>Michelle Bottino left her corporate career in 2018 to open a Fully Promoted store in Illinois. No industry experience. Within a few years, she'd built it into a million-dollar operation. Another franchisee in Ohio grew 72% in a single year.</p>

<p>Most of our successful owners came from completely different backgrounds. The system handles the heavy lifting - your job is building relationships with local businesses.</p>

<p>I'm putting together the first group of franchise partners for Ireland. Would love to include you in that conversation if the timing works.</p>

<p>Worth a quick chat?</p>

<p>Cheers,<br>
Prakash<br>
<a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Unit A20, Kingswood Business Park, Dublin</p>
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

<p><strong>1. "Do I need experience?"</strong> - No. Fully Promoted provides 4 weeks of intensive training and ongoing support. Many of our most successful franchisees came from completely unrelated industries.</p>

<p><strong>2. "What's the investment?"</strong> - The franchise fee is very competitive for a brand of this calibre, and the total investment includes a fully fitted-out, turnkey store ready to trade from day one.</p>

<p><strong>3. "Is there really a market for this in Ireland?"</strong> - Every business in Ireland needs branded products. Uniforms, corporate gifts, event merchandise, marketing materials. It's a large market and there's currently no dominant branded franchise serving it.</p>

<p>I'm allocating territories across Ireland right now - Dublin, Cork, Galway, Limerick, Waterford and beyond. Once they're assigned, they're gone.</p>

<p>If any of that sounds relevant, just reply and I'll send over the details. Happy to chat or just share the brochure - whatever works best.</p>

<p>Cheers,<br>
Prakash<br>
<a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Unit A20, Kingswood Business Park, Dublin</p>
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

<p>I've reached out a few times about Fully Promoted Ireland and haven't heard back, so I'll assume the timing isn't right.</p>

<p>Completely understand. If things change down the road, my door is always open. Just reply to this email anytime.</p>

<p>Wishing you all the best, {{FNAME}}.</p>

<p>Cheers,<br>
Prakash<br>
<a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>
Unit A20, Kingswood Business Park, Dublin</p>
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
