#!/usr/bin/env python3
"""
BNI Connect Global - Contact Scraper

Usage:
    python scrape_bni.py                           # Scrape all results (manual search)
    python scrape_bni.py --config configs/uk.json  # Use country config
    python scrape_bni.py --max 3                   # Test with 3 contacts
    python scrape_bni.py -o output.csv             # Custom output file
    python scrape_bni.py --list-configs             # Show all country configs + status
"""

import argparse
import csv
import json
import re
import time
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SCRIPT_DIR = Path(__file__).parent
DEFAULT_OUTPUT = SCRIPT_DIR / "bni_contacts.csv"
BNI_URL = "https://www.bniconnectglobal.com"

CSV_FIELDS = [
    "name", "email", "phone", "company", "chapter", "city",
    "postcode", "country", "specialty", "website", "address",
    "professional_details", "profile_url"
]


def load_config(config_path):
    """Load a country config JSON file."""
    with open(config_path) as f:
        return json.load(f)


def list_configs():
    """List all country configs and their status."""
    configs_dir = SCRIPT_DIR / "configs"
    if not configs_dir.exists():
        print("No configs/ directory found.")
        return

    configs = sorted(configs_dir.glob("*.json"))
    if not configs:
        print("No config files found in configs/")
        return

    print(f"\n{'Country':<20} {'Code':<12} {'Status':<14} {'Last Scraped':<14} {'Members':<10}")
    print("-" * 70)
    for cfg_path in configs:
        cfg = load_config(cfg_path)
        print(
            f"{cfg.get('country_name', '?'):<20} "
            f"{cfg.get('country_code', '?'):<12} "
            f"{cfg.get('status', '?'):<14} "
            f"{cfg.get('last_scraped') or '-':<14} "
            f"{cfg.get('total_members') or '-':<10}"
        )
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape BNI Connect contacts")
    parser.add_argument("--config", "-c", type=str, help="Country config JSON file (e.g. configs/uk.json)")
    parser.add_argument("--region", "-r", type=str, help="Region/state within the country (e.g. 'London', 'South East')")
    parser.add_argument("--all-regions", action="store_true", help="Loop through all regions in config (login once, scrape all)")
    parser.add_argument("--output", "-o", type=str, default=None)
    parser.add_argument("--max", "-m", type=int, default=0, help="Max contacts (0=all)")
    parser.add_argument("--skip", "-s", type=int, default=0, help="Skip first N profiles (resume from where you left off)")
    parser.add_argument("--existing", "-e", type=str, default=None, help="Existing CSV to build on (skip profiles already scraped with email)")
    parser.add_argument("--list-configs", action="store_true", help="List all country configs")
    return parser.parse_args()


def wait_for_login(page, config=None, region=None):
    """Wait for user to log in, then auto-search if config is provided."""
    page.goto(BNI_URL, wait_until="networkidle")
    print("\n" + "=" * 60)
    print(" BNI Connect Scraper")
    print("=" * 60)

    if config:
        country = config.get("country_name", "?")
        searches = config.get("searches", [])
        keyword = searches[0].get("keyword", "") if searches else ""
        print(f"\n Country: {country}")
        if region:
            print(f" Region:  {region}")
        print(f" Keyword: '{keyword}'" if keyword else " Keyword: (none — all members)")

    print("\n In the browser window:")
    print("   1. Log in to BNI Connect")
    print("   2. Wait until you see the dashboard/home page")
    print("\n" + "=" * 60)
    input("\n>>> Press Enter AFTER you are logged in... ")

    if config:
        _auto_search(page, config, region)
    else:
        print("\n Now manually search in the browser.")
        input("\n>>> Press Enter when search results are visible... ")


def _auto_search(page, config, region=None):
    """Automatically navigate to search, fill filters, and execute search."""
    country = config.get("country_name", "")
    searches = config.get("searches", [])
    keyword = searches[0].get("keyword", "") if searches else ""

    # Step 1: Navigate to Find a Member / Member Search
    print("\n[*] Navigating to member search...")
    search_url = "https://www.bniconnectglobal.com/web/dashboard/search"
    try:
        page.goto(search_url, wait_until="networkidle", timeout=30_000)
        time.sleep(2)
    except PlaywrightTimeout:
        print("[!] Search page load timed out, trying anyway...")

    # Step 2: Select country from dropdown
    print(f"[*] Setting country: {country}")
    _select_dropdown(page, "Country", country)
    time.sleep(1)

    # Step 3: Select region if provided (dropdown appears after country)
    if region:
        print(f"[*] Setting region: {region}")
        time.sleep(2)  # wait for region dropdown to populate
        _select_dropdown(page, "State", region)
        time.sleep(1)

    # Step 4: Fill keyword if provided
    if keyword:
        print(f"[*] Setting keyword: {keyword}")
        try:
            # Look for keyword/search input field
            keyword_input = page.query_selector(
                'input[placeholder*="eyword"], input[placeholder*="earch"], '
                'input[placeholder*="ame"], input[aria-label*="eyword"], '
                'input[aria-label*="earch"]'
            )
            if keyword_input:
                keyword_input.click()
                keyword_input.fill(keyword)
            else:
                # Try finding by label text
                page.evaluate("""
                    (kw) => {
                        const inputs = document.querySelectorAll('input[type="text"]');
                        for (const inp of inputs) {
                            const label = inp.closest('label') || inp.parentElement;
                            const text = label ? label.innerText.toLowerCase() : '';
                            if (text.includes('keyword') || text.includes('search') || text.includes('name')) {
                                inp.value = kw;
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                return;
                            }
                        }
                    }
                """, keyword)
        except Exception as e:
            print(f"[!] Could not set keyword: {e}")

    # Step 5: Click the Search button
    print("[*] Clicking Search...")
    try:
        # Try multiple selectors for the search button
        search_btn = (
            page.query_selector('button:has-text("Search")') or
            page.query_selector('button:has-text("search")') or
            page.query_selector('button[type="submit"]') or
            page.query_selector('input[type="submit"]')
        )
        if search_btn:
            search_btn.click()
            print("[*] Search clicked! Waiting for results...")
            time.sleep(5)
        else:
            # Try pressing Enter as fallback
            page.keyboard.press("Enter")
            print("[*] Pressed Enter to search. Waiting for results...")
            time.sleep(5)
    except Exception as e:
        print(f"[!] Could not click search: {e}")
        input("\n>>> Please click Search manually, then press Enter here... ")

    # Wait for results to appear (longer timeout for large country searches)
    try:
        page.wait_for_selector('a[href*="networkHome?userId="]', timeout=30_000)
        print("[+] Search results loaded!")
        # Extra wait for large searches to let initial batch render
        time.sleep(3)
    except PlaywrightTimeout:
        print("[!] No results detected yet.")
        input("\n>>> Press Enter if results are showing (or fix search manually)... ")


def _select_dropdown(page, label_hint, value):
    """Select a value from a MUI/React dropdown by label hint.

    BNI Connect uses MUI Select components. Strategy:
    1. Find the dropdown by label text
    2. Click to open it
    3. Find and click the option matching value
    """
    try:
        # Strategy 1: Find MUI Select by aria-label or nearby label text
        opened = page.evaluate("""
            (args) => {
                const [labelHint, value] = args;
                const hint = labelHint.toLowerCase();

                // Find all select-like elements (MUI uses div[role="button"] or similar)
                const selects = document.querySelectorAll(
                    'div[role="button"], div[role="combobox"], select, [class*="Select"], [class*="select"]'
                );

                for (const sel of selects) {
                    const container = sel.closest('[class*="formControl"], [class*="FormControl"], label, fieldset') || sel.parentElement;
                    const labelText = container ? container.innerText.toLowerCase() : '';

                    if (labelText.includes(hint)) {
                        sel.click();
                        return true;
                    }
                }

                // Fallback: look for actual <select> elements
                const nativeSelects = document.querySelectorAll('select');
                for (const sel of nativeSelects) {
                    const label = sel.closest('label') || sel.previousElementSibling;
                    const labelText = label ? label.innerText.toLowerCase() : '';
                    if (labelText.includes(hint) || sel.name?.toLowerCase().includes(hint)) {
                        // Set value directly for native select
                        for (const opt of sel.options) {
                            if (opt.text.includes(value)) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                    }
                }

                return false;
            }
        """, [label_hint, value])

        if opened:
            time.sleep(1)
            # Try to click the option in the dropdown menu
            try:
                # MUI renders dropdown options in a listbox
                option = page.query_selector(f'li:has-text("{value}")')
                if not option:
                    option = page.query_selector(f'[role="option"]:has-text("{value}")')
                if not option:
                    # Try partial match
                    option = page.evaluate("""
                        (value) => {
                            const items = document.querySelectorAll('li, [role="option"], [role="menuitem"]');
                            for (const item of items) {
                                if (item.innerText.trim().includes(value)) {
                                    item.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """, value)
                    if option:
                        return
                if option:
                    option.click()
                    return
            except Exception:
                pass

        # If auto-select failed, ask user
        print(f"[!] Could not auto-select {label_hint}='{value}'")
        input(f"    >>> Please select {label_hint}='{value}' manually, then press Enter... ")

    except Exception as e:
        print(f"[!] Dropdown error for {label_hint}: {e}")
        input(f"    >>> Please select {label_hint}='{value}' manually, then press Enter... ")


def scroll_to_load_all(page):
    """Scroll the inner results panel to load all results (infinite scroll).

    BNI Connect renders results in a scrollable inner panel (not the main window).
    We find the scrollable container that holds the member links and scroll it.
    """
    print("[*] Scrolling to load all results...")

    # First, find the scrollable container holding the results
    page.evaluate("""
        () => {
            // Find the container: walk up from the first member link
            // to find the nearest scrollable ancestor
            const firstLink = document.querySelector('a[href*="networkHome?userId="]');
            if (!firstLink) return;

            let el = firstLink;
            while (el && el !== document.body) {
                el = el.parentElement;
                if (el && el.scrollHeight > el.clientHeight + 100) {
                    // Mark it so we can find it again
                    el.setAttribute('data-scraper-scroll', 'true');
                    break;
                }
            }
        }
    """)

    prev_count = 0
    stable_rounds = 0
    max_stable = 15  # more patience for large country searches

    while stable_rounds < max_stable:
        current_count = page.evaluate("""
            () => document.querySelectorAll('a[href*="networkHome?userId="]').length
        """)

        if current_count == prev_count:
            stable_rounds += 1
            # Every 5 stable rounds, try clicking "Load More" / "Show More" buttons
            if stable_rounds % 5 == 0:
                clicked = page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button, a, span');
                        for (const b of btns) {
                            const txt = (b.innerText || '').toLowerCase();
                            if (txt.includes('load more') || txt.includes('show more') || txt.includes('view more') || txt.includes('next')) {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if clicked:
                    print(f"    Clicked 'Load More' button at {current_count} results...")
                    time.sleep(3)
                    stable_rounds = 0
                    continue
        else:
            stable_rounds = 0
            print(f"    {current_count} results loaded...")

        prev_count = current_count

        # Scroll the identified results container
        page.evaluate("""
            () => {
                // 1. Scroll the marked container
                const container = document.querySelector('[data-scraper-scroll="true"]');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }

                // 2. Also scroll last member link into view as backup
                const links = document.querySelectorAll('a[href*="networkHome?userId="]');
                if (links.length > 0) {
                    links[links.length - 1].scrollIntoView({behavior: 'smooth', block: 'end'});
                }

                // 3. Also try scrolling all overflow-y:auto/scroll containers
                const divs = document.querySelectorAll('div');
                for (const d of divs) {
                    const style = window.getComputedStyle(d);
                    const overflowY = style.overflowY;
                    if ((overflowY === 'auto' || overflowY === 'scroll') &&
                        d.scrollHeight > d.clientHeight + 100 &&
                        d.clientHeight > 200) {
                        d.scrollTop = d.scrollHeight;
                    }
                }

                // 4. Also scroll main window as last resort
                window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        time.sleep(2)

    print(f"[+] Total results: {prev_count}")
    return prev_count


def extract_search_results(page):
    """Extract all contacts from the MUI search results table.

    List view columns: Name | Chapter | Company | City | Profession and Specialty
    The Company column is only available here — detail pages don't show it.
    """
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
                    // List columns: Name | Chapter | Company | City | Specialty
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
    for attempt in range(3):
        try:
            page.goto(url, wait_until="networkidle", timeout=25_000)
            time.sleep(2)
            break
        except PlaywrightTimeout:
            return None
        except Exception as e:
            if attempt < 2:
                print(f"(retry {attempt+1}: {type(e).__name__})", end=" ", flush=True)
                time.sleep(5 * (attempt + 1))
            else:
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


def update_config(config_path, total_members):
    """Update config file with scrape results."""
    with open(config_path) as f:
        cfg = json.load(f)
    cfg["status"] = "done"
    cfg["last_scraped"] = str(date.today())
    cfg["total_members"] = total_members
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[+] Updated config: {config_path}")


def main():
    args = parse_args()

    if args.list_configs:
        list_configs()
        return

    # Load config if provided
    config = None
    config_path = None
    region = args.region
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists() and not config_path.is_absolute():
            config_path = SCRIPT_DIR / config_path
        config = load_config(config_path)
        country_code = config["country_code"]
        print(f"[*] Config: {config['country_name']} ({country_code})")
        if region:
            print(f"[*] Region: {region}")

    # Build list of regions to scrape
    if args.all_regions:
        if not config:
            print("ERROR: --all-regions requires --config")
            return
        regions_list = config.get("regions", [])
        if not regions_list:
            print("ERROR: No regions defined in config")
            return
        scraped = config.get("regions_scraped", [])
        remaining = [r for r in regions_list if r not in scraped]
        if not remaining:
            print("[+] All regions already scraped! Use merge_countries.py to combine.")
            return
        print(f"[*] Will scrape {len(remaining)} regions: {', '.join(remaining)}")
        print(f"    (Already done: {', '.join(scraped) if scraped else 'none'})")
    else:
        regions_list = [region] if region else [None]
        remaining = regions_list

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Step 1: User logs in (once)
        page.goto(BNI_URL, wait_until="networkidle")
        print("\n" + "=" * 60)
        print(" BNI Connect Scraper")
        print("=" * 60)
        if config:
            print(f"\n Country: {config['country_name']}")
            if args.all_regions:
                print(f" Mode:    ALL REGIONS ({len(remaining)} remaining)")
            elif region:
                print(f" Region:  {region}")
        print("\n Log in to BNI Connect in the browser window.")
        print("=" * 60)
        input("\n>>> Press Enter AFTER you are logged in... ")

        grand_total = 0

        for region_idx, current_region in enumerate(remaining):
            # Determine output path for this region
            if args.output and not args.all_regions:
                output_path = args.output
            elif config:
                today = date.today().strftime("%Y%m%d")
                if current_region:
                    region_slug = current_region.lower().replace(" ", "_").replace("&", "and")
                    output_path = str(SCRIPT_DIR / "output" / "raw" / f"{country_code}_{region_slug}_{today}.csv")
                else:
                    output_path = str(SCRIPT_DIR / "output" / "raw" / f"{country_code}_{today}.csv")
            else:
                output_path = str(DEFAULT_OUTPUT)

            if args.all_regions:
                print(f"\n{'#' * 60}")
                print(f"# Region {region_idx+1}/{len(remaining)}: {current_region}")
                print(f"# Output: {output_path}")
                print(f"{'#' * 60}")

            # Auto-search for this region
            if config:
                _auto_search(page, config, current_region)
            elif not args.all_regions:
                print("\n Manually search in the browser.")
                input("\n>>> Press Enter when search results are visible... ")

            # Scroll to load all results (automatic)
            scroll_to_load_all(page)

            # Extract from search results
            print("[*] Reading search results...")
            results = extract_search_results(page)
            print(f"[+] Found {len(results)} contacts")

            if not results:
                print("[-] No results found for this region.")
                page.screenshot(path=str(SCRIPT_DIR / f"debug_{current_region or 'main'}.png"))
                continue

            # Inject country from config
            if config:
                for r in results:
                    if not r.get("country"):
                        r["country"] = config["country_name"]

            if args.max > 0:
                results = results[:args.max]
                print(f"[*] Limited to {args.max} contacts (--max)")

            # Load existing data if provided (to skip already-scraped profiles)
            existing_names = set()
            existing_rows = {}
            if args.existing:
                import csv as csv_mod
                try:
                    with open(args.existing) as ef:
                        for row in csv_mod.DictReader(ef):
                            name_key = row.get("name", "").strip().lower()
                            if name_key:
                                existing_names.add(name_key)
                                if row.get("email", "").strip():
                                    existing_rows[name_key] = row
                    print(f"[*] Loaded {len(existing_names)} existing contacts ({len(existing_rows)} with email) from {args.existing}")
                except Exception as e:
                    print(f"[!] Could not load existing file: {e}")

            # Visit each profile
            print(f"\n[*] Visiting {len(results)} profiles for email/phone...\n")
            contacts = []

            for i, basic in enumerate(results):
                name = basic.get("name", "?")
                url = basic.get("profile_url", "")
                name_key = name.strip().lower()
                print(f"  [{i+1}/{len(results)}] {name}...", end=" ", flush=True)

                # Skip if already scraped with email in existing file
                if name_key in existing_rows:
                    merged = {**basic, **existing_rows[name_key]}
                    contacts.append(merged)
                    print(f"-> {existing_rows[name_key].get('email', '')} (from existing)")
                    continue

                if args.skip and i < args.skip:
                    print("(skipped - resume)")
                    contacts.append(basic)
                    continue

                if not url:
                    print("(no link)")
                    contacts.append(basic)
                    continue

                profile_data = extract_profile(page, url)
                if profile_data:
                    list_only_fields = {"company", "city", "specialty"}
                    merged = {**basic}
                    for k, v in profile_data.items():
                        if not v:
                            continue
                        if k in list_only_fields and merged.get(k):
                            continue
                        merged[k] = v
                    contacts.append(merged)
                    email = merged.get("email", "")
                    print(f"-> {email}" if email else "(no email)")
                else:
                    contacts.append(basic)
                    print("(timeout)")

                # Save progress every 10
                if (i + 1) % 10 == 0:
                    save_csv(contacts, output_path)
                    print(f"  --- Progress saved: {i+1} contacts ---")

                time.sleep(0.5)

            # Save this region's results
            save_csv(contacts, output_path)

            emails = sum(1 for c in contacts if c.get("email"))
            phones = sum(1 for c in contacts if c.get("phone"))
            companies = sum(1 for c in contacts if c.get("company"))
            grand_total += len(contacts)

            print(f"\n{'=' * 50}")
            if current_region:
                print(f" DONE — {current_region}")
            else:
                print(f" DONE!")
            print(f"   Total:     {len(contacts)} contacts")
            print(f"   Emails:    {emails}")
            print(f"   Phones:    {phones}")
            print(f"   Companies: {companies}")
            print(f"   File:      {output_path}")
            print(f"{'=' * 50}")

            # Update config: mark region as scraped
            if config and config_path and current_region:
                with open(config_path) as f:
                    cfg = json.load(f)
                if "regions_scraped" not in cfg:
                    cfg["regions_scraped"] = []
                if current_region not in cfg["regions_scraped"]:
                    cfg["regions_scraped"].append(current_region)
                cfg["status"] = "in_progress" if len(cfg["regions_scraped"]) < len(cfg.get("regions", [])) else "done"
                cfg["last_scraped"] = str(date.today())
                with open(config_path, "w") as f:
                    json.dump(cfg, f, indent=2)

        # Final summary for all-regions mode
        if args.all_regions:
            print(f"\n{'=' * 60}")
            print(f" ALL REGIONS COMPLETE — {config['country_name']}")
            print(f"   Total contacts across all regions: {grand_total}")
            print(f"   Run: python merge_countries.py --country {country_code}")
            print(f"{'=' * 60}")
        elif config and config_path and not region:
            update_config(config_path, grand_total)

        browser.close()


if __name__ == "__main__":
    main()
