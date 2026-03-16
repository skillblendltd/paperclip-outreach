#!/usr/bin/env python3
"""
BNI Connect Global - Contact Scraper

Usage:
    python scrape_bni.py                # Scrape all results
    python scrape_bni.py --max 3        # Test with 3 contacts
    python scrape_bni.py -o output.csv  # Custom output file
"""

import argparse
import csv
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

DEFAULT_OUTPUT = Path(__file__).parent / "bni_contacts.csv"
BNI_URL = "https://www.bniconnectglobal.com"

CSV_FIELDS = [
    "name", "email", "phone", "company", "chapter", "city",
    "postcode", "country", "specialty", "website", "address",
    "professional_details", "profile_url"
]


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape BNI Connect contacts")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max", "-m", type=int, default=0, help="Max contacts (0=all)")
    return parser.parse_args()


def wait_for_login(page):
    page.goto(BNI_URL, wait_until="networkidle")
    print("\n" + "=" * 60)
    print(" BNI Connect Scraper")
    print("=" * 60)
    print("\n In the browser window:")
    print("   1. Log in to BNI Connect")
    print("   2. Search for 'promotion' + 'United Kingdom'")
    print("   3. Make sure results are showing")
    print("   4. Come back here and press Enter")
    print("\n" + "=" * 60)
    input("\n>>> Press Enter when search results are visible... ")


def scroll_to_load_all(page):
    """Scroll to load all results (infinite scroll)."""
    print("[*] Scrolling to load all results...")
    prev_count = 0
    stable_rounds = 0

    while stable_rounds < 5:
        current_count = page.evaluate("""
            () => document.querySelectorAll('a[href*="networkHome?userId="]').length
        """)

        if current_count == prev_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            print(f"    {current_count} results loaded...")

        prev_count = current_count
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

    print(f"[+] Total results: {prev_count}")
    return prev_count


def extract_search_results(page):
    """Extract all contacts from the MUI search results."""
    results = page.evaluate("""
        () => {
            // Get ALL member links
            const allLinks = document.querySelectorAll('a[href*="networkHome?userId="]');
            const contacts = [];

            for (const link of allLinks) {
                const name = link.innerText.trim();
                const url = link.href;
                if (!name || !url) continue;

                // Walk up to find the row - look for the container that has
                // sibling rows (the list container's direct children)
                let row = link;
                for (let i = 0; i < 15; i++) {
                    row = row.parentElement;
                    if (!row || !row.parentElement) break;
                    const siblingCount = row.parentElement.children.length;
                    if (siblingCount > 5) break;
                }

                // Get the text content of the row, split by newlines
                if (row) {
                    const text = row.innerText.trim();
                    const parts = text.split('\\n').map(s => s.trim()).filter(s => s && s !== '+');

                    // Find name position and take fields after it
                    const nameIdx = parts.indexOf(name);
                    const fields = nameIdx >= 0 ? parts.slice(nameIdx + 1) : [];

                    contacts.push({
                        name: name,
                        profile_url: url,
                        chapter: fields[0] || '',
                        company: fields[1] || '',
                        city: fields[2] || '',
                        specialty: fields[3] || ''
                    });
                } else {
                    contacts.push({name, profile_url: url});
                }
            }

            return contacts;
        }
    """)
    return results


def extract_profile(page, url):
    """Visit a profile page and extract email, phone, website, etc."""
    try:
        page.goto(url, wait_until="networkidle", timeout=25_000)
        time.sleep(2)
    except PlaywrightTimeout:
        return None

    data = {}
    body_text = page.inner_text("body")

    # Email
    email_el = page.query_selector("a[href^='mailto:']")
    if email_el:
        data["email"] = (email_el.get_attribute("href") or "").replace("mailto:", "").strip()
    else:
        m = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', body_text)
        if m and "bniconnect" not in m.group(0):
            data["email"] = m.group(0)

    # Phone - UK numbers from body text
    phone_matches = re.findall(r'(?:0|\+44)[\d\s\-]{9,15}', body_text)
    if phone_matches:
        seen = set()
        phones = []
        for ph in phone_matches:
            cleaned = re.sub(r'[\s\-]', '', ph)
            if cleaned not in seen:
                seen.add(cleaned)
                phones.append(ph.strip())
        data["phone"] = "; ".join(phones)

    # Website - external link, skip social/bni
    skip = ["bni", "facebook", "linkedin", "twitter", "instagram", "google", "youtube", "tiktok"]
    links = page.query_selector_all("a[href^='http']")
    for link in links:
        href = link.get_attribute("href") or ""
        if href and not any(d in href.lower() for d in skip):
            data["website"] = href
            break

    # City, Postcode, Country - find label then grab next element's text
    for label, field in [("City", "city"), ("Post Code", "postcode"), ("Country", "country")]:
        try:
            val = page.evaluate("""
                (label) => {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    while (walker.nextNode()) {
                        if (walker.currentNode.textContent.trim() === label) {
                            let el = walker.currentNode.parentElement;
                            let next = el.nextElementSibling;
                            if (next) return next.innerText.trim();
                            next = el.parentElement.nextElementSibling;
                            if (next) return next.innerText.trim();
                        }
                    }
                    return '';
                }
            """, label)
            if val and len(val) < 50:
                data[field] = val
        except Exception:
            pass

    # Chapter from breadcrumb (e.g. "United Kingdom > Bristol > BNI Hadlee (Bristol)")
    chapter_match = re.search(r'>\s*(BNI\s+[\w\s()&\'-]+?)(?:\n|-Member|-Vice|$)', body_text)
    if chapter_match:
        data["chapter"] = chapter_match.group(1).strip()

    # Professional Details - grab the full section
    prof_match = re.search(r'Professional Details\n([\s\S]+?)(?:\nTraining History|\nGroups|\nMy Bio|\nPhotos|$)', body_text)
    if prof_match:
        prof_text = prof_match.group(1).strip()
        lines = [l.strip() for l in prof_text.split('\n') if l.strip()]
        if lines:
            data["specialty"] = lines[0]
            data["professional_details"] = " | ".join(lines)

    # Address - text near the map/location icon, look for UK postcode pattern
    addr_match = re.search(r'([\d\w\s,]+?[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})', body_text)
    if addr_match:
        addr = addr_match.group(1).strip()
        if len(addr) < 150:
            data["address"] = addr

    return data


def save_csv(contacts, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for c in contacts:
            writer.writerow({k: c.get(k, "") for k in CSV_FIELDS})


def main():
    args = parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Step 1: User logs in and sets up search
        wait_for_login(page)

        # Step 2: Scroll to load all results
        scroll_to_load_all(page)
        input("\n>>> Press Enter to start scraping profiles... ")

        # Step 3: Extract from search results
        print("[*] Reading search results...")
        results = extract_search_results(page)
        print(f"[+] Found {len(results)} contacts")

        if not results:
            print("[-] No results found.")
            page.screenshot(path=str(Path(__file__).parent / "debug.png"))
            browser.close()
            return

        if args.max > 0:
            results = results[:args.max]
            print(f"[*] Limited to {args.max} contacts (--max)")

        # Step 4: Visit each profile
        print(f"\n[*] Visiting {len(results)} profiles for email/phone...\n")
        contacts = []

        for i, basic in enumerate(results):
            name = basic.get("name", "?")
            url = basic.get("profile_url", "")
            print(f"  [{i+1}/{len(results)}] {name}...", end=" ", flush=True)

            if not url:
                print("(no link)")
                contacts.append(basic)
                continue

            profile_data = extract_profile(page, url)
            if profile_data:
                merged = {**basic, **{k: v for k, v in profile_data.items() if v}}
                contacts.append(merged)
                email = merged.get("email", "")
                print(f"-> {email}" if email else "(no email)")
            else:
                contacts.append(basic)
                print("(timeout)")

            # Save progress every 10
            if (i + 1) % 10 == 0:
                save_csv(contacts, args.output)
                print(f"  --- Progress saved: {i+1} contacts ---")

            time.sleep(0.5)

        # Final save
        save_csv(contacts, args.output)

        emails = sum(1 for c in contacts if c.get("email"))
        phones = sum(1 for c in contacts if c.get("phone"))
        print(f"\n{'=' * 50}")
        print(f" DONE!")
        print(f"   Total:  {len(contacts)} contacts")
        print(f"   Emails: {emails}")
        print(f"   Phones: {phones}")
        print(f"   File:   {args.output}")
        print(f"{'=' * 50}")

        browser.close()


if __name__ == "__main__":
    main()
