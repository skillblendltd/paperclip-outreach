#!/usr/bin/env python3
"""
Send Fully Promoted Dublin — BNI Ireland Print & Promo outreach.

Single warm email to fellow BNI members across Ireland.
Personalised by segment (trades, professional services, marketing, etc.)
Focus: relationship building, 1-2-1, referral partnership.

Usage:
    python3 send_bni_promo.py                    # Send to all unsent (status=new)
    python3 send_bni_promo.py --dry-run           # Preview without sending
    python3 send_bni_promo.py --segment trades    # Only trades segment
    python3 send_bni_promo.py --max 20            # Max 20 emails
    python3 send_bni_promo.py --status             # Show campaign stats
"""

import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error

API_BASE = "http://localhost:8002/api"
CAMPAIGN_ID = "3c46cbea-a817-43d5-9532-caecb2e7f01d"

CALENDAR_LINK = "https://calendar.app.google/yFLeFoyP3XscHsBs8"

# ---------------------------------------------------------------------------
# Segment-specific lines (inserted into the template)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Email template
# ---------------------------------------------------------------------------

SUBJECTS = {
    "A": "{{FNAME}}, 1-2-1?",
    "B": "Quick hello from a fellow BNI member, {{FNAME}}",
}

BODY_HTML = """
<p>Hi {{FNAME}},</p>

<p>I'm Prakash from BNI Dublin. I saw you're in {{CHAPTER}} and thought I'd reach out.</p>

<p>I'm trying to get to know more members outside my own chapter. Fancy a quick 1-2-1? Always great to meet a fellow member.</p>

<p>Here's a link to grab a time that suits: <a href="{{CALENDAR_LINK}}">Book a 1-2-1 with Prakash</a></p>

<p>Cheers,<br>
Prakash Inani<br>
Unit A20, Kingswood Business Park, D22 PC78<br>
Phone: (+353) 01-485-1205<br>
Mobile: (+353) 89-4781643<br>
Email: prakash@fullypromoted.ie<br>
Website: <a href="https://fullypromoted.ie">www.fullypromoted.ie</a></p>
""".strip()


def ab_variant(prospect_id):
    """Deterministic A/B assignment via MD5 hash."""
    h = hashlib.md5(str(prospect_id).encode()).hexdigest()
    return "A" if int(h, 16) % 2 == 0 else "B"


def get_prospects(segment=None):
    """Fetch eligible prospects (status=new) from the campaign."""
    params = f"campaign_id={CAMPAIGN_ID}&has_email=true&status=new&limit=500"
    if segment:
        params += f"&segment={segment}"
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


def send_email(prospect_id, subject, body_html, variant):
    """Send a single email via the outreach API."""
    payload = {
        "campaign_id": CAMPAIGN_ID,
        "prospect_id": prospect_id,
        "subject": subject,
        "body_html": body_html,
        "sequence_number": 1,
        "template_name": "bni_promo_intro",
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
        print(f"\nERROR: Could not reach API - {e}")
        print("Is the outreach server running on http://localhost:8002 ?")
        return

    print(f"\n{'=' * 55}")
    print(f"  Campaign: {status['campaign']}")
    print(f"  Sending:  {'ON' if status['sending_enabled'] else 'OFF'}")
    print(f"  From:     {status['from_name']} <{status['from_email']}>")
    print(f"{'=' * 55}")

    for item in status.get("status_breakdown", []):
        print(f"  {item['status']:20s} {item['count']:>5d}")
    print(f"{'=' * 55}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Send FP Dublin BNI Print & Promo emails"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--segment", type=str, help="Filter by segment")
    parser.add_argument("--max", type=int, default=999, help="Max emails to send")
    parser.add_argument("--status", action="store_true", help="Show campaign stats")
    parser.add_argument("--gap", type=int, default=8, help="Seconds between sends")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    prospects = get_prospects(segment=args.segment)

    if not prospects:
        print("No eligible prospects found (status=new).")
        return

    print(f"\nFound {len(prospects)} eligible prospects")
    if args.segment:
        print(f"  Segment filter: {args.segment}")
    print(f"  Max to send: {args.max}")
    print(f"  Dry run: {args.dry_run}")
    print()

    sent = 0
    errors = 0

    for p in prospects:
        if sent >= args.max:
            print(f"\nReached max ({args.max}). Stopping.")
            break

        pid = p["id"]
        fname = p.get("decision_maker_name", "").strip() or "there"
        chapter = p.get("region", "").strip() or "BNI"

        variant = ab_variant(pid)
        subject = SUBJECTS[variant].replace("{{FNAME}}", fname)

        body = (
            BODY_HTML
            .replace("{{FNAME}}", fname)
            .replace("{{CHAPTER}}", chapter)
            .replace("{{CALENDAR_LINK}}", CALENDAR_LINK)
        )

        label = f"{fname} <{p['email']}>"
        if chapter:
            label += f" ({chapter})"

        if args.dry_run:
            print(f"  DRY RUN: {label}")
            print(f"    Subject ({variant}): {subject}")
            print()
            sent += 1
            continue

        try:
            result = send_email(pid, subject, body, variant)
            status = result.get("status", "unknown")
            print(f"  SENT: {label} -> {status}")
            sent += 1
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            print(f"  ERROR: {label} -> {e.code} {error_body[:100]}")
            errors += 1
        except Exception as e:
            print(f"  ERROR: {label} -> {e}")
            errors += 1

        if not args.dry_run and sent < args.max:
            time.sleep(args.gap)

    print(f"\nDone. Sent: {sent}, Errors: {errors}")


if __name__ == "__main__":
    main()
