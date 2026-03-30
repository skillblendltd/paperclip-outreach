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
# Signature — short for cold outreach, full for replies
# Cold emails sign off as just "Prakash" (peer tone)
# ---------------------------------------------------------------------------
SIGNATURE_PEER = '<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>'  # Seq 1-2: peer tone with link

SIGNATURE_FOUNDER = '<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>'  # Seq 3-5: adds credibility

SIGNATURE_FULL = (  # For replies to engaged prospects (used by email-expert)
    '<p>Best regards,<br>'
    'Prakash Inani<br>'
    'Founder, <a href="https://taggiq.com/">TaggIQ</a><br>'
    'Kingswood Business Park, Dublin<br>'
    '<a href="https://taggiq.com/">https://taggiq.com</a></p>'
)

# ---------------------------------------------------------------------------
# Templates v2 — conversation-first, product-later
# Sequence: Question -> Shared Pain -> Invitation -> Social Proof -> Breakup
# Timing: Day 0, Day 7, Day 16, Day 28, Day 42
# Every email under 100 words. No pitch in Email 1.
# ---------------------------------------------------------------------------
TEMPLATES = {
    # ------------------------------------------------------------------
    # SEQ 1: Conversation Starter (Day 0)
    # Zero product mention. One specific question. Get a reply.
    # ------------------------------------------------------------------
    1: {
        "A": {
            "subject": "quick question about {{COMPANY}}",
            "template_name": "bni_v2_seq1_question",
        },
        "B": {
            "subject": "{{FNAME}}, how do you handle artwork approvals?",
            "template_name": "bni_v2_seq1_question_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>Spotted you on BNI Connect, looks like we\'re both in the print and promo world.</p>'
            '<p>Quick question: how does your team handle artwork approvals? '
            'I\'ve talked to a bunch of BNI members recently and it\'s wild how many '
            'are still chasing approvals over email and WhatsApp.</p>'
            '<p>Curious if you\'ve found something that works or if it\'s still a pain.</p>'
            + SIGNATURE_PEER
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 2: Shared Pain (Day 7)
    # Share insight from conversations. Introduce "I built a tool" naturally.
    # ------------------------------------------------------------------
    2: {
        "A": {
            "subject": "the artwork approval problem",
            "template_name": "bni_v2_seq2_pain",
        },
        "B": {
            "subject": "{{FNAME}}, thought you'd find this interesting",
            "template_name": "bni_v2_seq2_pain_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>Thought you might find this interesting. I asked about 20 BNI members in print '
            'and promo how they handle artwork approvals and order tracking. Almost everyone said '
            'some version of "email back and forth until someone finally says yes."</p>'
            '<p>I actually built a tool to fix this for my own shop in Dublin. It\'s called '
            '<a href="https://taggiq.com/">TaggIQ</a> and it connects quotes, '
            'approvals, orders and invoicing in one place. Happy to share what I learned if '
            'you\'re dealing with the same thing.</p>'
            '<p>Either way, no worries.</p>'
            + SIGNATURE_PEER
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 3: Design Partner Invitation (Day 16)
    # Clear offer, clear scarcity, clear ask. 70 words.
    # ------------------------------------------------------------------
    3: {
        "A": {
            "subject": "would you want input on this?",
            "template_name": "bni_v2_seq3_partner",
        },
        "B": {
            "subject": "looking for 5 BNI members to help shape this",
            "template_name": "bni_v2_seq3_partner_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>I\'m building a system specifically for print and promo shops, quotes, artwork '
            'approvals, orders, invoicing, all in one place. It\'s called '
            '<a href="https://taggiq.com/">TaggIQ</a>.</p>'
            '<p>I\'m looking for 5 BNI members to be design partners: tell me what slows your '
            'team down, and I\'ll build around your workflow. As a fellow BNI member, I\'d love '
            'to offer you 3 months free to try it out, no commitment, no card required.</p>'
            '<p>2 spots taken. Worth a 15-min chat?</p>'
            + SIGNATURE_FOUNDER
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 4: Social Proof (Day 28)
    # Specific results from real shops. Low-pressure walkthrough offer.
    # ------------------------------------------------------------------
    4: {
        "A": {
            "subject": "from 4 tools to 1 screen",
            "template_name": "bni_v2_seq4_proof",
        },
        "B": {
            "subject": "{{FNAME}}, quick update from BNI print shops",
            "template_name": "bni_v2_seq4_proof_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>Quick update. A few print and promo shops in BNI started using '
            '<a href="https://taggiq.com/">TaggIQ</a> over the past month.</p>'
            '<p>One team told me they went from using four different tools per order to one screen, '
            'quote to invoice. Another said artwork approvals that used to take days over email '
            'now close in hours.</p>'
            '<p>If you\'re ever curious, happy to show you in 15 minutes. No pitch, just a walkthrough.</p>'
            '<p>Either way, always great being connected through BNI.</p>'
            + SIGNATURE_FOUNDER
        ),
    },
    # ------------------------------------------------------------------
    # SEQ 5: Breakup (Day 42)
    # Shortest email. Permission-based close.
    # ------------------------------------------------------------------
    5: {
        "A": {
            "subject": "should I stop reaching out?",
            "template_name": "bni_v2_seq5_breakup",
        },
        "B": {
            "subject": "{{FNAME}}, one last one",
            "template_name": "bni_v2_seq5_breakup_name",
        },
        "body_html": (
            '<p>Hi {{FNAME}},</p>'
            '<p>I know how busy things get running a shop, so I\'ll keep this short.</p>'
            '<p>Is streamlining your workflow something you\'d want to explore, or would you '
            'prefer I stop reaching out? Either way is completely fine.</p>'
            + SIGNATURE_FOUNDER
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
        # Seq 1: Embroidery-specific question
        1: {
            "A": {
                "subject": "quick question about {{COMPANY}}",
                "template_name": "bni_emb_v2_seq1_question",
            },
            "B": {
                "subject": "{{FNAME}}, how do you collect sizes for big orders?",
                "template_name": "bni_emb_v2_seq1_question_name",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>Spotted you on BNI Connect, looks like we\'re both in the decorated apparel world.</p>'
                '<p>Quick question: how does your team collect sizes when a customer orders uniforms '
                'for 30-40 staff? I\'ve talked to a bunch of BNI members recently and most are still '
                'chasing sizes across emails, WhatsApp and spreadsheets.</p>'
                '<p>Curious if you\'ve found something that works or if it\'s still a headache.</p>'
                + SIGNATURE_PEER
            ),
        },
        # Seq 2: Embroidery-specific shared pain
        2: {
            "A": {
                "subject": "the size collection problem",
                "template_name": "bni_emb_v2_seq2_pain",
            },
            "B": {
                "subject": "{{FNAME}}, thought you'd find this interesting",
                "template_name": "bni_emb_v2_seq2_pain_name",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>Thought you might find this interesting. I asked about 20 BNI members in '
                'embroidery and decorated apparel how they handle size collection and artwork approvals. '
                'Almost everyone said some version of "chase them over email for days."</p>'
                '<p>I actually built a tool to fix this for my own shop in Dublin. It handles quotes, '
                'size collection, artwork approvals, orders and invoicing in one place. Happy to share '
                'what I learned if you\'re dealing with the same thing.</p>'
                '<p>Either way, no worries.</p>'
                + SIGNATURE_PEER
            ),
        },
        # Seq 3: Same partner offer, embroidery framing
        3: {
            "A": {
                "subject": "would you want input on this?",
                "template_name": "bni_emb_v2_seq3_partner",
            },
            "B": {
                "subject": "looking for 5 BNI members to help shape this",
                "template_name": "bni_emb_v2_seq3_partner_name",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>I\'m building a system specifically for embroidery and apparel shops, quotes, '
                'size collection, artwork approvals, orders, invoicing, all in one place. It\'s called '
                '<a href="https://taggiq.com/">TaggIQ</a>.</p>'
                '<p>I\'m looking for 5 BNI members to be design partners: tell me what slows your '
                'team down, and I\'ll build around your workflow. As a fellow BNI member, I\'d love '
                'to offer you 3 months free to try it out, no commitment, no card required.</p>'
                '<p>2 spots taken. Worth a 15-min chat?</p>'
                + SIGNATURE_FOUNDER
            ),
        },
        # Seq 4: Embroidery-specific proof
        4: {
            "A": {
                "subject": "from 4 tools to 1 screen",
                "template_name": "bni_emb_v2_seq4_proof",
            },
            "B": {
                "subject": "{{FNAME}}, quick update from BNI apparel shops",
                "template_name": "bni_emb_v2_seq4_proof_name",
            },
            "body_html": (
                '<p>Hi {{FNAME}},</p>'
                '<p>Quick update. A few embroidery and apparel shops in BNI started using '
                '<a href="https://taggiq.com/">TaggIQ</a> over the past month.</p>'
                '<p>One team told me they went from using four different tools per order to one screen, '
                'quote to invoice. Another said size collection that used to take days of chasing '
                'now happens through a single link.</p>'
                '<p>If you\'re ever curious, happy to show you in 15 minutes. No pitch, just a walkthrough.</p>'
                '<p>Either way, always great being connected through BNI.</p>'
                + SIGNATURE_FOUNDER
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
