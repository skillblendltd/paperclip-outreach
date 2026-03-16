#!/usr/bin/env python3
"""
BNI Email Sequence Sender - sends all 5 sequences across all BNI campaigns.
Calls paperclip-outreach API on localhost:8002.

Usage:
    python3 send_sequence.py                        # Send all due sequences, all campaigns
    python3 send_sequence.py --campaign bni          # Only TaggIQ BNI (UK)
    python3 send_sequence.py --campaign embroidery   # Only Embroidery Global
    python3 send_sequence.py --campaign promo        # Only Promo Global
    python3 send_sequence.py --dry-run               # Preview without sending
    python3 send_sequence.py --status                # Show campaign stats

Sequence (BNI Psychology):
    1. Peer Story     (Day 0)  - "One of them" framing, relatable pain
    2. Curiosity      (Day 5)  - No pitch, shared pain, community seed
    3. Design Partner (Day 10) - Highest-converting, scarcity + BNI ethos
    4. Social Proof   (Day 15) - Quantified pain, real partner results
    5. Breakup        (Day 21) - Permission-based close, highest open rate

All safeguards enforced by the API (daily limit, min gap, sequence order, suppression).
"""
import argparse
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_BASE = "http://localhost:8002/api"

# ---------------------------------------------------------------------------
# Campaign IDs
# ---------------------------------------------------------------------------
CAMPAIGNS = {
    "bni": {
        "id": "64ed1454-18fc-4783-9438-da18143f7312",
        "name": "TaggIQ BNI (UK)",
    },
    "embroidery": {
        "id": "9dc977d3-f793-4051-905c-30c82b76dcd6",
        "name": "TaggIQ BNI Embroidery Global",
    },
    "promo": {
        "id": "9cdc1870-476b-4bfe-91ff-9661bd62c662",
        "name": "TaggIQ BNI Promo Global",
    },
}

# ---------------------------------------------------------------------------
# Signature (shared across all emails)
# ---------------------------------------------------------------------------
SIGNATURE = (
    '<p>Best regards,<br>'
    'Prakash Inani<br>'
    'Founder, <a href="https://taggiq.com/">TaggIQ</a><br>'
    'Kingswood Business Park, Dublin</p>'
)

# ---------------------------------------------------------------------------
# Templates - 5 BNI-warm sequences with A/B subject line variants
# Body is identical for A/B (only subject differs) to keep it genuine.
# ---------------------------------------------------------------------------
TEMPLATES = {
    # ------------------------------------------------------------------
    # SEQ 1: Peer Story (Day 0)
    # "One of them" framing. BNI trust signal first. Pain before product.
    # ------------------------------------------------------------------
    1: {
        "A": {
            "subject": "Fellow BNI member in print and promo",
            "template_name": "bni_seq1_peer",
        },
        "B": {
            "subject": "{{FNAME}}, quick one from a fellow BNI member",
            "template_name": "bni_seq1_peer_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>Hope you\'re well. I came across your profile on BNI Connect and noticed '
            'we\'re both in the print and promo space, so I thought I\'d say hello.</p>'
            '<p>I run a print and promo shop in Dublin, and one thing that always drove me mad '
            'was having everything in different places. Quotes in one tool, artwork approvals '
            'over email, purchase orders somewhere else, and then re-entering everything into '
            'Xero at the end. The same order getting typed four different times.</p>'
            '<p>In the end, I built something to solve it for our own shop. It\'s called '
            '<a href="https://taggiq.com/">TaggIQ</a> and it connects the whole journey from '
            'quote to invoice in one place, built specifically for how print and promo '
            'businesses actually work.</p>'
            '<p>I\'d be really interested to hear how you\'re managing this at {{COMPANY}}. '
            'Always great to learn how other BNI members in the industry handle their workflow.</p>'
            '<p>If you\'re curious, I\'d be happy to share what we built. No pressure at all.</p>'
            + SIGNATURE
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 2: Curiosity (Day 5)
    # No pitch. Shared pain conversation. BNI community group seed.
    # ------------------------------------------------------------------
    2: {
        "A": {
            "subject": "Quick question for fellow BNI print shops",
            "template_name": "bni_seq2_curiosity",
        },
        "B": {
            "subject": "{{FNAME}}, curious how other BNI members handle this",
            "template_name": "bni_seq2_curiosity_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>I\'ve been chatting with a few BNI members in the print and promo space over '
            'the past couple of weeks. It\'s been eye-opening how differently everyone runs '
            'things - spreadsheets, Xero workarounds, DecoNetwork, even WhatsApp threads for '
            'artwork approvals.</p>'
            '<p>One thing that keeps coming up: a customer approves a quote three weeks later, '
            'and the team has to go hunting for supplier pricing all over again because nothing '
            'was saved in one place.</p>'
            '<p>Does that happen in your business, or have you found a way around it?</p>'
            '<p>I\'m also trying to connect a small group of print and promo owners inside BNI '
            'who are interested in sharing best practices. If that sounds useful, happy to '
            'loop you in.</p>'
            + SIGNATURE
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 3: Design Partner Invitation (Day 10)
    # Highest-converting. BNI ethos of helping members build things.
    # Scarcity without pressure. Clear value prop (40% off).
    # ------------------------------------------------------------------
    3: {
        "A": {
            "subject": "Small group forming - curious if you'd be interested",
            "template_name": "bni_seq3_partner",
        },
        "B": {
            "subject": "Looking for a few industry partners",
            "template_name": "bni_seq3_partner_alt",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>After speaking with a number of BNI members in print and promo, the same '
            'operational pain points keep surfacing - quoting takes too long, artwork approvals '
            'get lost in email, and supplier orders end up being re-entered into accounting '
            'manually.</p>'
            '<p>Because of that, I\'m putting together a small group of design partners - '
            'five businesses in the industry who want to help shape what we\'re building at '
            '<a href="https://taggiq.com/">TaggIQ</a>.</p>'
            '<p>What that looks like:</p>'
            '<ul>'
            '<li>You tell us what slows your team down</li>'
            '<li>We build features around your actual workflow</li>'
            '<li>You get early access and founding-partner pricing (40% off the first year)</li>'
            '</ul>'
            '<p>I\'m keeping this to five businesses so we can give each one proper attention. '
            'Two spots are already taken.</p>'
            '<p>If that sounds interesting, I\'d love to show you what we\'ve built so far and '
            'hear how your team currently works. Happy to jump on a quick 15-minute call '
            'whenever suits.</p>'
            + SIGNATURE
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 4: Social Proof + Soft Close (Day 15)
    # Quantified pain (30-60 min/order). Real partner results.
    # BNI warmth in closing.
    # ------------------------------------------------------------------
    4: {
        "A": {
            "subject": "Something I keep hearing from print shops",
            "template_name": "bni_seq4_proof",
        },
        "B": {
            "subject": "Interesting pattern from BNI promo businesses",
            "template_name": "bni_seq4_proof_alt",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>Something interesting has come up in conversations with print and promo '
            'businesses over the past few weeks.</p>'
            '<p>Several teams told me they spend anywhere from 30 minutes to an hour per order '
            're-entering the same information - moving from quotes to artwork approvals to '
            'supplier orders and then copying it all into Xero or QuickBooks.</p>'
            '<p>A few early partners are now running that entire flow through '
            '<a href="https://taggiq.com/">TaggIQ</a>. One team told me their quote-to-invoice '
            'process went from touching four different tools to one screen.</p>'
            '<p>If you\'re ever curious to see how it works, I\'m happy to give you a quick '
            'walkthrough - no commitment, just 15 minutes.</p>'
            '<p>Either way, always great connecting with fellow BNI members in the industry.</p>'
            + SIGNATURE
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 5: Breakup (Day 21)
    # "Should I stop?" = highest open rate pattern. Permission-based close.
    # ------------------------------------------------------------------
    5: {
        "A": {
            "subject": "Should I stop reaching out?",
            "template_name": "bni_seq5_breakup",
        },
        "B": {
            "subject": "Should I stop reaching out, {{FNAME}}?",
            "template_name": "bni_seq5_breakup_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>I\'ve sent a few messages and I know how busy things get running a business, '
            'so I wanted to check - is this something you\'d like to hear more about, or would '
            'you prefer I stop reaching out?</p>'
            '<p>Either way is completely fine. Just didn\'t want to keep landing in your inbox '
            'if it\'s not relevant.</p>'
            + SIGNATURE
        ),
    },
}

SEQ_NAMES = {
    1: "Peer Story",
    2: "Curiosity",
    3: "Design Partner",
    4: "Social Proof",
    5: "Breakup",
}

# ---------------------------------------------------------------------------
# Campaign-specific template overrides
# Only need to specify fields that differ from the base TEMPLATES.
# Merged on top of base template at send time.
# ---------------------------------------------------------------------------
CAMPAIGN_OVERRIDES = {
    "embroidery": {
        # Seq 1: Broaden "print and promo" to include embroidery/apparel
        1: {
            "A": {
                "subject": "Fellow BNI member in decorated apparel",
                "template_name": "bni_emb_seq1_peer",
            },
            "B": {
                "subject": "{{FNAME}}, quick one from a fellow BNI member",
                "template_name": "bni_emb_seq1_peer_name",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>Hope you\'re well. I came across your profile on BNI Connect and noticed '
                'we\'re both in the decorated apparel and promo space, so I thought I\'d say hello.</p>'
                '<p>I run a print and promo shop in Dublin, and one thing that always drove me mad '
                'was having everything in different places. Quotes in one tool, artwork approvals '
                'over email, purchase orders somewhere else, and then re-entering everything into '
                'Xero at the end. The same order getting typed four different times.</p>'
                '<p>In the end, I built something to solve it for our own shop. It\'s called '
                '<a href="https://taggiq.com/">TaggIQ</a> and it connects the whole journey from '
                'quote to invoice in one place, built specifically for how businesses like ours '
                'actually work.</p>'
                '<p>I\'d be really interested to hear how you\'re managing this at {{COMPANY}}. '
                'Always great to learn how other BNI members in the industry handle their workflow.</p>'
                '<p>If you\'re curious, I\'d be happy to share what we built. No pressure at all.</p>'
                + SIGNATURE
            ),
        },
        # Seq 2: Full rewrite - embroidery-specific pain points
        2: {
            "A": {
                "subject": "Quick question for fellow BNI embroidery shops",
                "template_name": "bni_emb_seq2_curiosity",
            },
            "B": {
                "subject": "{{FNAME}}, curious how other BNI members handle this",
                "template_name": "bni_emb_seq2_curiosity_name",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>I\'ve been chatting with a few BNI members in the embroidery and decorated '
                'apparel space recently. It\'s interesting how differently everyone manages things '
                '- some use spreadsheets for size collection, others are chasing customers over '
                'email for logo placement approvals, and quite a few are still re-keying orders '
                'into Xero by hand.</p>'
                '<p>One thing that keeps coming up: a customer sends through a uniform order for '
                '40 staff, and the team ends up chasing sizes across emails, WhatsApp messages, '
                'and spreadsheets for days before they can even place a garment order.</p>'
                '<p>Does that happen at {{COMPANY}}, or have you found a better way?</p>'
                '<p>I\'m also connecting a small group of embroidery and apparel business owners '
                'inside BNI who want to share best practices. Happy to loop you in if that\'s useful.</p>'
                + SIGNATURE
            ),
        },
        # Seq 3: Tweak opening to reference embroidery pain points
        3: {
            "A": {
                "subject": "Small group forming - curious if you'd be interested",
                "template_name": "bni_emb_seq3_partner",
            },
            "B": {
                "subject": "Looking for a few industry partners",
                "template_name": "bni_emb_seq3_partner_alt",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>After speaking with a number of BNI members in embroidery and decorated apparel, '
                'the same operational pain points keep surfacing - quoting takes too long, size '
                'collection is a nightmare, and orders end up being re-entered into accounting '
                'manually.</p>'
                '<p>Because of that, I\'m putting together a small group of design partners - '
                'five businesses in the industry who want to help shape what we\'re building at '
                '<a href="https://taggiq.com/">TaggIQ</a>.</p>'
                '<p>What that looks like:</p>'
                '<ul>'
                '<li>You tell us what slows your team down</li>'
                '<li>We build features around your actual workflow</li>'
                '<li>You get early access and founding-partner pricing (40% off the first year)</li>'
                '</ul>'
                '<p>I\'m keeping this to five businesses so we can give each one proper attention. '
                'Two spots are already taken.</p>'
                '<p>If that sounds interesting, I\'d love to show you what we\'ve built so far and '
                'hear how your team currently works. Happy to jump on a quick 15-minute call '
                'whenever suits.</p>'
                + SIGNATURE
            ),
        },
        # Seq 4: Fix subject lines + tweak body for embroidery
        4: {
            "A": {
                "subject": "Something I keep hearing from embroidery businesses",
                "template_name": "bni_emb_seq4_proof",
            },
            "B": {
                "subject": "Interesting pattern from BNI apparel businesses",
                "template_name": "bni_emb_seq4_proof_alt",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>Something interesting has come up in conversations with embroidery and '
                'decorated apparel businesses over the past few weeks.</p>'
                '<p>Several teams told me they spend anywhere from 30 minutes to an hour per order '
                're-entering the same information - chasing sizes, confirming decoration specs, '
                'placing garment orders, and then copying it all into Xero or QuickBooks.</p>'
                '<p>A few early partners are now running that entire flow through '
                '<a href="https://taggiq.com/">TaggIQ</a>. One team told me their quote-to-invoice '
                'process went from touching four different tools to one screen.</p>'
                '<p>If you\'re ever curious to see how it works, I\'m happy to give you a quick '
                'walkthrough - no commitment, just 15 minutes.</p>'
                '<p>Either way, always great connecting with fellow BNI members in the industry.</p>'
                + SIGNATURE
            ),
        },
        # Seq 5: No override needed - breakup is universal
    },
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path):
    try:
        req = Request(f"{API_BASE}{path}")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError) as e:
        print(f"  ERROR: GET {path} failed: {e}")
        return None


def api_post(path, data):
    body = json.dumps(data).encode()
    req = Request(f"{API_BASE}{path}", data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()), resp.status
    except HTTPError as e:
        error_body = e.read().decode()
        try:
            return json.loads(error_body), e.code
        except json.JSONDecodeError:
            return {"error": error_body}, e.code


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def show_status(campaign_keys):
    for key in campaign_keys:
        cid = CAMPAIGNS[key]["id"]
        cname = CAMPAIGNS[key]["name"]
        status = api_get(f"/status/?campaign_id={cid}")
        if not status:
            print(f"\n=== {cname}: UNREACHABLE ===")
            continue

        print(f"\n=== {cname} ===")
        print(f"  Sending:         {'ON' if status['sending_enabled'] else 'OFF'}")
        print(f"  From:            {status['from_name']} <{status['from_email']}>")
        print(f"  Prospects:       {status['prospects_with_email']} with email")
        print(f"  Sent today:      {status['sent_today']} / {status['max_emails_per_day']}")
        print(f"  Remaining:       {status['remaining_today']}")
        print(f"  A/B stats:       A={status['ab_stats']['A']}, B={status['ab_stats']['B']}")
        safeguards = status.get("safeguards", {})
        print(f"  Max/prospect:    {safeguards.get('max_per_prospect', '?')}")
        print(f"  Min gap:         {safeguards.get('min_gap_minutes', '?')}m")

        # Prospect breakdown
        for st in ["new", "contacted", "engaged", "interested", "demo_scheduled", "not_interested", "opted_out"]:
            prospects = api_get(f"/prospects/?campaign_id={cid}&status={st}&has_email=true&limit=1")
            if prospects and prospects["count"] > 0:
                print(f"    {st}: {prospects['count']}")


# ---------------------------------------------------------------------------
# Sending logic
# ---------------------------------------------------------------------------

def send_campaign_sequences(campaign_key, dry_run=False):
    """Send all eligible sequences for a single campaign."""
    cid = CAMPAIGNS[campaign_key]["id"]
    cname = CAMPAIGNS[campaign_key]["name"]

    # Check campaign status
    status = api_get(f"/status/?campaign_id={cid}")
    if not status:
        print(f"\nERROR: Cannot reach API for {cname}")
        return 0, 0

    if not status["sending_enabled"]:
        print(f"\n{cname}: Sending DISABLED. Enable in admin.")
        return 0, 0

    remaining = status["remaining_today"]
    if remaining <= 0:
        print(f"\n{cname}: Daily limit reached.")
        return 0, 0

    print(f"\n{'=' * 60}")
    print(f"  {cname}")
    print(f"  Remaining today: {remaining} | A/B: A={status['ab_stats']['A']}, B={status['ab_stats']['B']}")
    print(f"{'=' * 60}")

    sent_total = 0
    errors_total = 0

    # --- Sequence 1: new prospects ---
    new_prospects = api_get(f"/prospects/?campaign_id={cid}&status=new&has_email=true&limit=500")
    seq1_list = new_prospects["prospects"] if new_prospects else []

    if seq1_list:
        s, e = send_sequence(1, seq1_list, cid, dry_run, remaining - sent_total, campaign_key)
        sent_total += s
        errors_total += e

    # --- Sequences 2-5: contacted prospects ---
    contacted = api_get(f"/prospects/?campaign_id={cid}&status=contacted&has_email=true&limit=500")
    followup_list = contacted["prospects"] if contacted else []

    if followup_list:
        for seq_num in range(2, 6):
            if sent_total >= remaining:
                print(f"  Daily limit reached after {sent_total} sends.")
                break
            s, e = send_sequence(seq_num, followup_list, cid, dry_run, remaining - sent_total, campaign_key)
            sent_total += s
            errors_total += e

    return sent_total, errors_total


def get_template(seq_num, campaign_key):
    """Get template for a sequence, with campaign-specific overrides if they exist."""
    base = TEMPLATES[seq_num]
    overrides = CAMPAIGN_OVERRIDES.get(campaign_key, {}).get(seq_num)
    if overrides:
        return overrides
    return base


def send_sequence(seq_num, prospects, campaign_id, dry_run, remaining, campaign_key="bni"):
    """Send a single sequence to eligible prospects. Returns (sent, errors)."""
    label = SEQ_NAMES.get(seq_num, f"Seq {seq_num}")
    template = get_template(seq_num, campaign_key)
    body_html = template["body_html"]

    print(f"\n  --- Seq {seq_num}: {label} ({len(prospects)} prospects) ---")

    sent = 0
    errors = 0

    for p in prospects:
        if sent >= remaining:
            print(f"    Daily limit reached.")
            break

        # Determine A/B variant (use ab_variant from API if available)
        variant = p.get("ab_variant", "A")
        subject = template[variant]["subject"]
        template_name = template[variant]["template_name"]

        if dry_run:
            extra = f" [emails_sent={p.get('emails_sent', 0)}]"
            print(f"    [DRY] seq {seq_num}/{variant} -> {p['business_name']} ({p['email']}){extra}")
            sent += 1
            continue

        # Wait between sends (API enforces min_gap, but we add a buffer)
        if sent > 0:
            time.sleep(5)

        payload = {
            "campaign_id": campaign_id,
            "prospect_id": p["id"],
            "subject": subject,
            "body_html": body_html,
            "sequence_number": seq_num,
            "template_name": template_name,
            "ab_variant": variant,
        }

        try:
            result, code = api_post("/send/", payload)
        except Exception as e:
            print(f"    ERROR {p['business_name']}: {e}")
            errors += 1
            time.sleep(10)
            continue

        if code == 200 and result.get("status") == "sent":
            print(f"    SENT seq {seq_num}/{variant} -> {p['business_name']} ({p['email']})")
            sent += 1
        elif code == 429:
            wait = result.get("wait_seconds", 60)
            print(f"    Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            # Retry once
            try:
                result, code = api_post("/send/", payload)
                if code == 200 and result.get("status") == "sent":
                    print(f"    SENT seq {seq_num}/{variant} -> {p['business_name']} ({p['email']}) (retry)")
                    sent += 1
                else:
                    print(f"    FAILED (retry) {p['business_name']}: {result.get('error', '')}")
                    errors += 1
            except Exception as e:
                print(f"    ERROR (retry) {p['business_name']}: {e}")
                errors += 1
        elif code == 403:
            reason = result.get("error", "")
            # These are expected - prospect not eligible yet for this sequence
            if any(x in reason for x in ["already sent", "not sent yet", "already received", "Follow-up emails only"]):
                pass  # Silent skip - normal for batch processing
            else:
                print(f"    SKIP {p['business_name']}: {reason}")
        else:
            print(f"    FAILED {p['business_name']}: {result.get('error', '')} (HTTP {code})")
            errors += 1

    if sent > 0 or (not dry_run and errors > 0):
        print(f"    Seq {seq_num} done: {sent} sent, {errors} errors")

    return sent, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="BNI Email Sequence Sender - all 5 sequences, all campaigns"
    )
    parser.add_argument(
        "--campaign", "-c",
        choices=["bni", "embroidery", "promo", "all"],
        default="all",
        help="Which campaign to process (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--status", action="store_true", help="Show campaign stats")
    args = parser.parse_args()

    if args.campaign == "all":
        campaign_keys = list(CAMPAIGNS.keys())
    else:
        campaign_keys = [args.campaign]

    if args.status:
        show_status(campaign_keys)
        return

    print("BNI Email Sequence Sender")
    print(f"Campaigns: {', '.join(CAMPAIGNS[k]['name'] for k in campaign_keys)}")
    if args.dry_run:
        print("MODE: DRY RUN (no emails will be sent)")

    total_sent = 0
    total_errors = 0

    for key in campaign_keys:
        s, e = send_campaign_sequences(key, dry_run=args.dry_run)
        total_sent += s
        total_errors += e

    print(f"\n{'=' * 60}")
    print(f"  ALL DONE {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  Total sent:   {total_sent}")
    print(f"  Total errors: {total_errors}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
