#!/usr/bin/env python3
"""Send Email 1 to TaggIQ Ireland — Signs & Signage contacts (100/day batch).

Send window: Tuesday–Thursday, 9am–5pm Irish time.
Sort order: Dublin / Cork first, then rest of Ireland.
Segment:    signs

Usage:
    cd /Users/pinani/Documents/paperclip-outreach
    venv/bin/python google-maps-scraper/send_ireland_signs_seq1.py
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
import pytz

# ── Config ──────────────────────────────────────────────────────────────────
API_BASE    = "http://localhost:8002/api"
CAMPAIGN_ID = "74de42a1-5bab-4e31-ada8-c200b18f1403"
BATCH_SIZE  = 100
SEGMENT     = "signs"

# Send window: Tue–Thu only, between 9am and 5pm Irish time
IRISH_TZ       = pytz.timezone("Europe/Dublin")
SEND_DAYS      = {1, 2, 3}   # Mon=0 … Sun=6 — Tuesday=1, Wednesday=2, Thursday=3
SEND_HOUR_MIN  = 9
SEND_HOUR_MAX  = 17

# Priority cities (sent first within each batch)
PRIORITY_CITIES = {"dublin", "cork"}

# ── Templates ───────────────────────────────────────────────────────────────
SUBJECT_A = "quick question about {{COMPANY}}"
SUBJECT_B = "a question for the team at {{COMPANY}}"

BODY_HTML = """\
<p>Hi there,</p>

<p>I spent 20 years in software before moving into print and signage,
and one thing that struck me was how manual the approval process
still is for most shops.</p>

<p>Quick question: how does your team handle design approvals before
a job goes to production? For vehicle wraps and bespoke installs
especially, a missed detail at approval stage can be expensive to
fix after the fact.</p>

<p>Curious how you manage it.</p>

<p>If this isn't something you handle, feel free to pass it along to whoever looks after production workflow.</p>

<p>Prakash</p>\
"""


# ── Helpers ─────────────────────────────────────────────────────────────────

def check_send_window():
    """Return True if it is currently within the allowed send window."""
    now = datetime.now(IRISH_TZ)
    if now.weekday() not in SEND_DAYS:
        day_name = now.strftime("%A")
        print(f"[!] Today is {day_name} — send window is Tuesday to Thursday only.")
        print("    Run again on Tuesday, Wednesday, or Thursday.")
        return False
    if not (SEND_HOUR_MIN <= now.hour < SEND_HOUR_MAX):
        print(f"[!] Current Irish time is {now.strftime('%H:%M')} — send window is 09:00–17:00.")
        return False
    return True


def city_priority(prospect):
    """Lower number = higher priority (Dublin/Cork first)."""
    city = (prospect.get("city") or "").lower().strip()
    return 0 if city in PRIORITY_CITIES else 1


def get_prospects():
    url = f"{API_BASE}/prospects/?campaign_id={CAMPAIGN_ID}&limit=2000"
    resp = urllib.request.urlopen(urllib.request.Request(url))
    return json.loads(resp.read()).get("prospects", [])


def send_email(prospect_id, subject, ab_variant):
    payload = {
        "campaign_id":   CAMPAIGN_ID,
        "prospect_id":   prospect_id,
        "subject":       subject,
        "body_html":     BODY_HTML,
        "sequence_number": 1,
        "template_name": "ireland_signs_email_1",
        "ab_variant":    ab_variant,
    }
    req = urllib.request.Request(
        f"{API_BASE}/send/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if CAMPAIGN_ID == "REPLACE_WITH_SIGNS_CAMPAIGN_ID":
        print("[!] CAMPAIGN_ID not set — edit this script and fill in the campaign UUID.")
        sys.exit(1)

    if not check_send_window():
        sys.exit(0)

    prospects = get_prospects()

    # Filter: new only, segment match
    to_send = [
        p for p in prospects
        if p.get("emails_sent", 0) == 0
        and p.get("segment") == SEGMENT
    ]

    # Sort: Dublin/Cork first
    to_send.sort(key=city_priority)

    batch = to_send[:BATCH_SIZE]

    print(f"[*] Campaign:          TaggIQ Ireland — Signs & Signage (Seq 1)")
    print(f"[*] Segment:           {SEGMENT}")
    print(f"[*] Total unsent:      {len(to_send)}")
    print(f"[*] Sending today:     {len(batch)}")
    print(f"[*] Remaining after:   {len(to_send) - len(batch)}")
    print()

    if not batch:
        print("Nothing to send today.")
        return

    sent = failed = 0

    for i, p in enumerate(batch):
        pid   = p["id"]
        name  = p.get("decision_maker_name") or p.get("business_name", "?")
        email = p.get("email", "?")
        biz   = p.get("business_name", "?")
        city  = p.get("city", "")

        subject = SUBJECT_A if i % 2 == 0 else SUBJECT_B
        variant = "A" if i % 2 == 0 else "B"

        label = f"{biz}, {city}" if city else biz
        print(f"  [{i+1}/{len(batch)}] {name} ({label}) <{email}>...", end=" ", flush=True)

        try:
            result = send_email(pid, subject, variant)
            status = result.get("status", "unknown")
            if status == "sent":
                sent += 1
                print(f"SENT [{variant}]")
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

        time.sleep(60)  # 60s delay between sends

    print(f"\n{'=' * 55}")
    print(f"  DONE — Signs Seq 1")
    print(f"  Sent:      {sent}")
    print(f"  Failed:    {failed}")
    print(f"  Remaining: {len(to_send) - len(batch)}")
    print(f"  Run again next Tue/Wed/Thu for next batch of 100")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
