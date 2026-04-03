#!/usr/bin/env python3
"""
Unified London Cold Outreach Sequence Sender
Handles all 5 sequences for all 3 London TaggIQ cold campaigns.
Runs autonomously — enforces send window, 7-day gaps, sequence order.

Campaigns:
  - TaggIQ London — Signs & Signage       (8a20de08)
  - TaggIQ London — Apparel & Embroidery  (10635a74)
  - TaggIQ London — Print & Promo         (cdd2dc0f)

Usage:
    venv/bin/python google-maps-scraper/send_london_sequences.py
    venv/bin/python google-maps-scraper/send_london_sequences.py --dry-run
    venv/bin/python google-maps-scraper/send_london_sequences.py --campaign signs
    venv/bin/python google-maps-scraper/send_london_sequences.py --status
"""

import argparse
import json
import time
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone as tz
import pytz

API_BASE   = "http://localhost:8002/api"
BATCH_SIZE = 100
MIN_GAP_DAYS = 7

UK_TZ         = pytz.timezone("Europe/London")
SEND_DAYS     = {0, 1, 2, 3, 4}   # Mon–Fri
SEND_HOUR_MIN = 10
SEND_HOUR_MAX = 17

PRIORITY_CITIES = {"london", "central london"}

# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------
CAMPAIGNS = {
    "signs": {
        "id": "8a20de08-42cb-4d69-bae7-f7d2a39d5429",
        "name": "TaggIQ London — Signs & Signage",
        "segments": {"signs"},
    },
    "apparel": {
        "id": "10635a74-89f6-4ebe-b6f7-febae9963e3e",
        "name": "TaggIQ London — Apparel & Embroidery",
        "segments": {"apparel_embroidery"},
    },
    "print": {
        "id": "cdd2dc0f-5c2d-46c3-8cc4-5c6160b92e7b",
        "name": "TaggIQ London — Print & Promo",
        "segments": {"promo_distributor", "print_shop"},
    },
}

SIGNATURE = (
    '<p>Prakash<br>'
    'Founder, <a href="https://taggiq.com">TaggIQ</a><br>'
    '<a href="https://taggiq.com">taggiq.com</a></p>'
)

SIGNATURE_FULL = (
    '<p>Prakash<br>'
    'Founder, TaggIQ<br>'
    '<a href="https://taggiq.com">taggiq.com</a></p>'
)

# ---------------------------------------------------------------------------
# Templates — Non-BNI, cold outreach, London market
# NEVER mention Fully Promoted. No BNI references.
# Trust signal: "20 years in software before moving into this industry"
# ---------------------------------------------------------------------------
TEMPLATES = {
    # ── Signs-specific templates ────────────────────────────────────────────
    "signs": {
        1: {
            "A": {"subject": "quick question about {{COMPANY}}", "template_name": "london_signs_seq1_a"},
            "B": {"subject": "a question for the team at {{COMPANY}}", "template_name": "london_signs_seq1_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I spent 20 years in software before moving into print and signage, "
                "and one thing that struck me was how manual the approval process still is.</p>"
                "<p>Quick question: how does your team handle design approvals before a job goes "
                "to production? For vehicle wraps and bespoke installs especially, a missed detail "
                "at approval stage can be expensive to fix.</p>"
                "<p>Curious how you manage it.</p>"
                "<p>If this isn't something you handle, feel free to pass it along to whoever "
                "looks after production workflow.</p>"
                + SIGNATURE
            ),
        },
        2: {
            "A": {"subject": "the approval problem in signage", "template_name": "london_signs_seq2_a"},
            "B": {"subject": "{{FNAME}}, thought this might be relevant", "template_name": "london_signs_seq2_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I've been talking with sign shop owners across London about how they handle "
                "design approvals and job tracking. Most describe some version of "
                "chasing clients over email or WhatsApp until they finally say yes.</p>"
                "<p>I built a tool to fix this. It's called "
                '<a href="https://taggiq.com">TaggIQ</a> and it keeps quotes, artwork approvals, '
                "orders and invoicing in one place.</p>"
                "<p>Happy to share more if you're dealing with the same thing.</p>"
                + SIGNATURE
            ),
        },
        3: {
            "A": {"subject": "why I built TaggIQ", "template_name": "london_signs_seq3_a"},
            "B": {"subject": "a different approach to running a sign shop", "template_name": "london_signs_seq3_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I spent about 20 years working in software before getting into the signage and "
                "print industry, and when I saw how far behind the tools were compared to other "
                "sectors, I wanted to build something better.</p>"
                '<p>That\'s why I built <a href="https://taggiq.com">TaggIQ</a>, a platform '
                "designed for shops like yours. Quotes, artwork approvals, orders, invoicing, "
                "all in one place.</p>"
                "<p>If you're curious, I'd love to offer you a free trial. No commitment, "
                "no card required.</p>"
                '<p>You can sign up at <a href="https://taggiq.com/signup">taggiq.com</a> or '
                "book a quick 15-minute walkthrough:</p>"
                '<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>'
                + SIGNATURE_FULL
            ),
        },
        4: {
            "A": {"subject": "artwork approvals over email = costly mistakes", "template_name": "london_signs_seq4_a"},
            "B": {"subject": "one thing most sign shops get wrong", "template_name": "london_signs_seq4_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>If your team is still chasing design approvals over email, you know the risk. "
                "Clients forget to reply, a job goes to production on an old file, and the "
                "reprint is on you.</p>"
                '<p>That\'s exactly why I built <a href="https://taggiq.com">TaggIQ</a>. '
                "Customers approve artwork in one click, you see the status instantly, "
                "and nothing falls through.</p>"
                "<p>Happy to show you how it works if it's ever on your radar.</p>"
                + SIGNATURE_FULL
            ),
        },
        5: {
            "A": {"subject": "last one from me", "template_name": "london_signs_seq5_a"},
            "B": {"subject": "last one from me", "template_name": "london_signs_seq5_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I've reached out a few times about streamlining job approvals for sign shops, "
                "so I'll keep this short.</p>"
                "<p>If it's ever something you'd like to explore, the door is always open. "
                'You can check out <a href="https://taggiq.com">TaggIQ</a> or book a quick chat:</p>'
                '<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>'
                "<p>Wishing you continued success with the business.</p>"
                + SIGNATURE_FULL
            ),
        },
    },

    # ── Apparel/Embroidery-specific templates ───────────────────────────────
    "apparel": {
        1: {
            "A": {"subject": "quick question about {{COMPANY}}", "template_name": "london_apparel_seq1_a"},
            "B": {"subject": "a question for the team at {{COMPANY}}", "template_name": "london_apparel_seq1_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I spent 20 years in software before moving into embroidery and decorated "
                "apparel, and one thing that surprised me was how far behind the tools were.</p>"
                "<p>Quick question: how does your team collect sizes when a customer orders "
                "uniforms for a group? Most shops I've spoken with across London are still "
                "chasing sizes over email and spreadsheets.</p>"
                "<p>Curious how you manage it.</p>"
                "<p>If this isn't something you handle, feel free to pass it along to whoever "
                "manages production workflow.</p>"
                + SIGNATURE
            ),
        },
        2: {
            "A": {"subject": "the size collection problem", "template_name": "london_apparel_seq2_a"},
            "B": {"subject": "{{FNAME}}, thought this might be relevant", "template_name": "london_apparel_seq2_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I've been talking with embroidery and apparel shop owners across London about "
                "how they handle size collection and artwork approvals. Almost everyone describes "
                "some version of chasing clients for days before a job can move forward.</p>"
                "<p>I built a tool to fix this. It's called "
                '<a href="https://taggiq.com">TaggIQ</a> and it handles quotes, size collection, '
                "artwork approvals, orders and invoicing in one place.</p>"
                "<p>Happy to share more if you're dealing with the same thing.</p>"
                + SIGNATURE
            ),
        },
        3: {
            "A": {"subject": "why I built TaggIQ", "template_name": "london_apparel_seq3_a"},
            "B": {"subject": "a different approach to running an apparel shop", "template_name": "london_apparel_seq3_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I spent about 20 years working in software before getting into the embroidery "
                "and decorated apparel industry, and when I saw how far behind the tools were, "
                "I wanted to build something better.</p>"
                '<p>That\'s why I built <a href="https://taggiq.com">TaggIQ</a>, a platform '
                "designed for shops like yours. Quotes, size collection, artwork approvals, "
                "orders and invoicing, all in one place.</p>"
                "<p>If you're curious, I'd love to offer you a free trial. No commitment, "
                "no card required.</p>"
                '<p>You can sign up at <a href="https://taggiq.com/signup">taggiq.com</a> or '
                "book a quick 15-minute walkthrough:</p>"
                '<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>'
                + SIGNATURE_FULL
            ),
        },
        4: {
            "A": {"subject": "size collection over email = nightmare", "template_name": "london_apparel_seq4_a"},
            "B": {"subject": "one thing most apparel shops get wrong", "template_name": "london_apparel_seq4_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>If your team is still chasing size charts and artwork approvals over email, "
                "you know the pain. Jobs get delayed, clients forget to reply, and things slip "
                "through the cracks.</p>"
                '<p>That\'s exactly why I built <a href="https://taggiq.com">TaggIQ</a>. '
                "Customers approve artwork and submit sizes in one place, you see the status "
                "instantly, and nothing falls through.</p>"
                "<p>Happy to show you how it works if it's ever on your radar.</p>"
                + SIGNATURE_FULL
            ),
        },
        5: {
            "A": {"subject": "last one from me", "template_name": "london_apparel_seq5_a"},
            "B": {"subject": "last one from me", "template_name": "london_apparel_seq5_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I've reached out a few times about streamlining size collection and artwork "
                "approvals for apparel shops, so I'll keep this short.</p>"
                "<p>If it's ever something you'd like to explore, the door is always open. "
                'You can check out <a href="https://taggiq.com">TaggIQ</a> or book a quick chat:</p>'
                '<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>'
                "<p>Wishing you continued success with the business.</p>"
                + SIGNATURE_FULL
            ),
        },
    },

    # ── Print & Promo templates ─────────────────────────────────────────────
    "print": {
        1: {
            "A": {"subject": "quick question about {{COMPANY}}", "template_name": "london_print_seq1_a"},
            "B": {"subject": "a question for the team at {{COMPANY}}", "template_name": "london_print_seq1_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I spent 20 years in software before moving into the print and promo "
                "industry, and one thing that surprised me was how far behind the tools "
                "were compared to every other sector.</p>"
                "<p>Quick question: how does your team handle artwork approvals? Most shops "
                "I've spoken with across London are still doing it over email and WhatsApp, "
                "which works until things start slipping through the cracks.</p>"
                "<p>Curious how you manage it.</p>"
                "<p>If this isn't something you handle, feel free to pass it along to whoever "
                "manages artwork and orders.</p>"
                + SIGNATURE
            ),
        },
        2: {
            "A": {"subject": "the artwork approval problem", "template_name": "london_print_seq2_a"},
            "B": {"subject": "{{FNAME}}, thought this might be relevant", "template_name": "london_print_seq2_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I've been talking with print and promo shop owners across London about how "
                "they handle artwork approvals and order tracking. Almost everyone describes some "
                "version of email back and forth until someone finally says yes.</p>"
                "<p>I built a tool to fix this. It's called "
                '<a href="https://taggiq.com">TaggIQ</a> and it keeps quotes, artwork approvals, '
                "orders and invoicing in one place.</p>"
                "<p>Happy to share more if you're dealing with the same thing.</p>"
                + SIGNATURE
            ),
        },
        3: {
            "A": {"subject": "why I built TaggIQ", "template_name": "london_print_seq3_a"},
            "B": {"subject": "a different approach to running a promo shop", "template_name": "london_print_seq3_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I spent about 20 years working in software before getting into the promo "
                "industry, and when I saw how far behind the tools were compared to other "
                "sectors, I wanted to build something better.</p>"
                '<p>That\'s why I built <a href="https://taggiq.com">TaggIQ</a>, a platform '
                "designed specifically for how promo shops actually run. Quotes, artwork "
                "approvals, orders, invoicing, all in one place.</p>"
                "<p>If you're curious, I'd love to offer you a free trial. No commitment, "
                "no card required.</p>"
                '<p>You can sign up at <a href="https://taggiq.com/signup">taggiq.com</a> or '
                "book a quick 15-minute walkthrough:</p>"
                '<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>'
                + SIGNATURE_FULL
            ),
        },
        4: {
            "A": {"subject": "artwork approvals over email = nightmare", "template_name": "london_print_seq4_a"},
            "B": {"subject": "one thing most promo shops get wrong", "template_name": "london_print_seq4_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>If your team is still chasing artwork approvals over email, you know the "
                "pain. Clients forget to reply, files get lost in threads, and things slip "
                "through the cracks.</p>"
                '<p>That\'s exactly why I built <a href="https://taggiq.com">TaggIQ</a>. '
                "Customers approve artwork in one click, you see the status instantly, "
                "and nothing falls through.</p>"
                "<p>Happy to show you how it works if it's ever on your radar.</p>"
                + SIGNATURE_FULL
            ),
        },
        5: {
            "A": {"subject": "last one from me", "template_name": "london_print_seq5_a"},
            "B": {"subject": "last one from me", "template_name": "london_print_seq5_b"},
            "body_html": (
                "<p>Hi there,</p>"
                "<p>I've reached out a few times about streamlining artwork approvals and "
                "order management for promo shops, so I'll keep this short.</p>"
                "<p>If it's ever something you'd like to explore, the door is always open. "
                'You can check out <a href="https://taggiq.com">TaggIQ</a> or book a quick chat:</p>'
                '<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>'
                "<p>Wishing you continued success with the business.</p>"
                + SIGNATURE_FULL
            ),
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_send_window():
    now = datetime.now(UK_TZ)
    if now.weekday() not in SEND_DAYS:
        print(f"[!] Today is {now.strftime('%A')} — send window is Mon–Fri only.")
        return False
    if not (SEND_HOUR_MIN <= now.hour < SEND_HOUR_MAX):
        print(f"[!] UK time is {now.strftime('%H:%M')} — window is {SEND_HOUR_MIN}:00–{SEND_HOUR_MAX}:00.")
        return False
    return True


def get_prospects(campaign_id):
    url = f"{API_BASE}/prospects/?campaign_id={campaign_id}&limit=5000"
    resp = urllib.request.urlopen(urllib.request.Request(url))
    return json.loads(resp.read()).get("prospects", [])


def send_email(campaign_id, prospect_id, seq_num, template_key, subject, body_html, ab_variant, dry_run):
    if dry_run:
        return {"status": "dry_run"}
    payload = {
        "campaign_id":     campaign_id,
        "prospect_id":     prospect_id,
        "subject":         subject,
        "body_html":       body_html,
        "sequence_number": seq_num,
        "template_name":   template_key,
        "ab_variant":      ab_variant,
    }
    req = urllib.request.Request(
        f"{API_BASE}/send/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def resolve_next_seq(prospect):
    """Return the next sequence number this prospect should receive, or None."""
    sent = prospect.get("emails_sent", 0)
    status = prospect.get("status", "")
    if not prospect.get("send_enabled", True):
        return None
    if status in ("opted_out", "opt_out", "not_interested", "demo_scheduled",
                  "interested", "engaged", "design_partner"):
        return None
    if status == "new" and sent == 0:
        return 1
    if status == "contacted" and 1 <= sent <= 4:
        return sent + 1
    return None


def is_gap_met(prospect):
    last = prospect.get("last_emailed_at")
    if not last:
        return True
    try:
        last_clean = last.replace("Z", "+00:00")
        last_dt = datetime.fromisoformat(last_clean)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=tz.utc)
        return (datetime.now(tz.utc) - last_dt).days >= MIN_GAP_DAYS
    except Exception:
        return True


def replace_vars(text, prospect):
    fname = (prospect.get("decision_maker_name") or "").split()[0] if prospect.get("decision_maker_name") else ""
    company = prospect.get("business_name", "")
    city = prospect.get("city", "")
    return (text
            .replace("{{FNAME}}", fname or "there")
            .replace("{{COMPANY}}", company)
            .replace("{{CITY}}", city))


# ---------------------------------------------------------------------------
# Send one campaign
# ---------------------------------------------------------------------------

def run_campaign(key, cfg, templates, dry_run):
    campaign_id = cfg["id"]
    campaign_name = cfg["name"]
    segments = cfg["segments"]

    prospects = get_prospects(campaign_id)
    eligible = [
        p for p in prospects
        if p.get("segment") in segments
        and p.get("send_enabled", True)
        and resolve_next_seq(p) is not None
        and is_gap_met(p)
    ]
    batch = eligible[:BATCH_SIZE]

    # Group by next seq for reporting
    from collections import Counter
    seq_breakdown = Counter(resolve_next_seq(p) for p in eligible if resolve_next_seq(p))

    print(f"\n{'='*60}")
    print(f"  {campaign_name}")
    print(f"  Ready to send: {len(eligible)} | Sending today: {len(batch)}")
    print(f"  Seq breakdown: {dict(sorted(seq_breakdown.items()))}")
    print(f"{'='*60}")

    if not batch:
        print("  Nothing to send today.\n")
        return 0, 0

    sent = failed = 0
    delay_range = (30, 60)

    for i, p in enumerate(batch):
        seq_num = resolve_next_seq(p)
        tmpl = templates.get(seq_num)
        if not tmpl:
            continue

        variant = "A" if i % 2 == 0 else "B"
        subject_raw = tmpl[variant]["subject"]
        template_key = tmpl[variant]["template_name"]
        body_html = tmpl["body_html"]

        subject = replace_vars(subject_raw, p)
        body_html = replace_vars(body_html, p)

        name = p.get("decision_maker_name") or p.get("business_name", "?")
        email = p.get("email", "?")
        biz = p.get("business_name", "?")

        print(f"  [{i+1}/{len(batch)}] Seq{seq_num} | {name} ({biz}) <{email}>...", end=" ", flush=True)

        if dry_run:
            print(f"DRY RUN [{variant}] — {subject}")
            sent += 1
            continue

        try:
            result = send_email(campaign_id, p["id"], seq_num, template_key,
                                subject, body_html, variant, dry_run)
            status = result.get("status", "unknown")
            if status == "sent":
                sent += 1
                print(f"SENT [Seq{seq_num}/{variant}]")
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
            time.sleep(30)

        import random
        time.sleep(random.randint(*delay_range))

    return sent, failed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--campaign", choices=["signs", "apparel", "print"], help="Run one campaign only")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    args = parser.parse_args()

    if args.status:
        for key, cfg in CAMPAIGNS.items():
            prospects = get_prospects(cfg["id"])
            from collections import Counter
            statuses = Counter(p.get("status") for p in prospects)
            ready = [p for p in prospects if resolve_next_seq(p) and is_gap_met(p)]
            print(f"\n{cfg['name']}")
            print(f"  Total: {len(prospects)} | Ready to send: {len(ready)}")
            print(f"  Statuses: {dict(statuses.most_common())}")
        return

    if not check_send_window():
        sys.exit(0)

    targets = {args.campaign: CAMPAIGNS[args.campaign]} if args.campaign else CAMPAIGNS

    total_sent = total_failed = 0
    print(f"\n[{datetime.now(UK_TZ).strftime('%Y-%m-%d %H:%M')} UK] London Campaign Runner")
    if args.dry_run:
        print("  *** DRY RUN — no emails will be sent ***")

    for key, cfg in targets.items():
        templates = TEMPLATES[key]
        s, f = run_campaign(key, cfg, templates, args.dry_run)
        total_sent += s
        total_failed += f

    print(f"\n{'='*60}")
    print(f"  ALL DONE — Sent: {total_sent} | Failed: {total_failed}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
