"""
Google Maps scraper using Playwright (FREE, no API key needed).
Navigates Google Maps search, scrolls results, extracts business data.
"""

import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from config import SEGMENT_MAP


class PlacesClient:
    """Scrapes Google Maps search results using headless Playwright."""

    MAPS_URL = "https://www.google.com/maps/search/{query}"

    def __init__(self, api_key=None, headless=True):
        """api_key is ignored (kept for interface compat). Uses Playwright."""
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        self._page = self._context.new_page()
        self._accepted_cookies = False

    def text_search(self, keyword, location, max_results=60):
        """
        Search Google Maps and extract business listings.
        Returns list of dicts with business data.
        """
        query = f"{keyword} in {location}"
        url = self.MAPS_URL.format(query=query.replace(" ", "+"))

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
        except PlaywrightTimeout:
            print(f"\n  [!] Timeout loading Google Maps for: {query}")
            return []

        # Handle cookie consent (EU)
        if not self._accepted_cookies:
            self._accept_cookies()

        # Wait for results to load
        time.sleep(2)

        # Scroll the results panel to load more
        results = self._scroll_and_collect(max_results, keyword, location)
        return results

    def _accept_cookies(self):
        """Dismiss Google cookie consent dialog if present."""
        try:
            # Try multiple selectors for the Accept button
            for selector in [
                'button:has-text("Accept all")',
                'button:has-text("Accept All")',
                'button:has-text("Reject all")',
                'form[action*="consent"] button:first-child',
                '[aria-label="Accept all"]',
            ]:
                btn = self._page.query_selector(selector)
                if btn:
                    btn.click()
                    self._accepted_cookies = True
                    time.sleep(2)
                    return
        except Exception:
            pass
        self._accepted_cookies = True

    def _scroll_and_collect(self, max_results, keyword, location):
        """Scroll the results panel and collect business cards."""
        results = []
        seen_names = set()

        # Find the scrollable results panel
        feed_selector = 'div[role="feed"]'
        try:
            self._page.wait_for_selector(feed_selector, timeout=10000)
        except PlaywrightTimeout:
            # Try alternative: the results might be in a different container
            feed_selector = 'div[role="main"]'
            try:
                self._page.wait_for_selector(feed_selector, timeout=5000)
            except PlaywrightTimeout:
                print("\n  [!] Could not find results panel")
                return []

        last_count = 0
        stale_rounds = 0

        for scroll_round in range(20):  # max 20 scroll attempts
            # Extract all visible business cards
            cards = self._extract_cards(keyword, location)

            for card in cards:
                name_key = card["business_name"].lower().strip()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    results.append(card)

            if len(results) >= max_results:
                results = results[:max_results]
                break

            # Check if we've hit the end
            end_marker = self._page.query_selector('span.HlvSq')
            if end_marker:
                break

            # Check for "You've reached the end of the list"
            end_text = self._page.query_selector('p.fontBodyMedium span:has-text("end of the list")')
            if end_text:
                break

            # Scroll down in the feed
            try:
                self._page.evaluate(f'''
                    const feed = document.querySelector('{feed_selector}');
                    if (feed) feed.scrollTop = feed.scrollHeight;
                ''')
            except Exception:
                pass

            time.sleep(2)

            # Stale check
            if len(results) == last_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
            else:
                stale_rounds = 0
            last_count = len(results)

        return results

    def _extract_cards(self, keyword, location):
        """Extract business data from all visible result cards."""
        cards = []

        try:
            # Each result card is an <a> tag with class "hfpxzc"
            elements = self._page.query_selector_all('a.hfpxzc')

            for el in elements:
                try:
                    name = el.get_attribute("aria-label") or ""
                    href = el.get_attribute("href") or ""
                    if not name:
                        continue

                    # Get the parent card container for more details
                    card_data = self._extract_card_details(el, name, href, keyword, location)
                    if card_data:
                        cards.append(card_data)
                except Exception:
                    continue

        except Exception:
            pass

        return cards

    def _extract_card_details(self, link_el, name, maps_url, keyword, location):
        """Extract detailed info from a single business card."""
        # Navigate up to the card container
        card = link_el.evaluate_handle(
            "el => el.closest('[jsaction]') || el.parentElement.parentElement"
        )

        phone = ""
        website = ""
        address = ""
        rating = 0
        review_count = 0
        category = ""

        try:
            # Get all text content from the card
            card_text = card.inner_text() if card else ""
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]

            for line in lines:
                # Rating: "4.5(123)" or "4.5 (123)"
                rating_match = re.match(r'^(\d+\.?\d*)\s*\((\d[\d,]*)\)', line)
                if rating_match:
                    rating = float(rating_match.group(1))
                    review_count = int(rating_match.group(2).replace(",", ""))
                    continue

                # Phone number patterns
                if re.match(r'^[\+\(]?\d[\d\s\-\(\)]{7,}$', line):
                    phone = line.strip()
                    continue

                # Address: contains street indicators or looks like an address
                if not address and any(x in line.lower() for x in [
                    " st", " rd", " ave", " dr", " blvd", " ln", " way",
                    " street", " road", " avenue", " drive", " place",
                    " park", " estate", " centre", " center",
                ]):
                    address = line
                    continue

                # Category: usually the line after rating, short text
                if not category and len(line) < 50 and not re.search(r'\d{3}', line):
                    if line.lower() != name.lower() and "open" not in line.lower() and "closed" not in line.lower():
                        if any(x in line.lower() for x in [
                            "print", "promo", "embroid", "screen", "sign",
                            "apparel", "clothing", "uniform", "advertis",
                            "graphic", "design", "merch", "gift", "trophy",
                            "engrav", "shop", "store", "service", "supplier",
                            "distributor", "agency", "studio",
                        ]):
                            category = line

        except Exception:
            pass

        # Determine segment
        segment = "promo_distributor"
        for kw, seg in SEGMENT_MAP.items():
            if kw in keyword.lower():
                segment = seg
                break

        # Parse city/region from address or location
        city, region = self._parse_location(address, location)

        return {
            "business_name": name,
            "address": address,
            "phone": phone,
            "website": "",  # filled by clicking into the listing or by email_extractor
            "rating": rating,
            "review_count": review_count,
            "business_category": category,
            "opening_hours": "",
            "city": city,
            "region": region,
            "latitude": "",
            "longitude": "",
            "google_maps_url": maps_url,
            "place_id": "",
            "source_query": f"{keyword} in {location}",
            "segment": segment,
            "email": "",
        }

    def _parse_location(self, address, search_location):
        """Extract city and region from address or fall back to search location."""
        if address:
            parts = [p.strip() for p in address.split(",")]
            if len(parts) >= 3:
                return (parts[-3], ", ".join(parts[-2:]))
            elif len(parts) == 2:
                return (parts[0], parts[1])

        # Fall back to search location
        loc_parts = [p.strip() for p in search_location.split(",")]
        if len(loc_parts) >= 2:
            return (loc_parts[0], loc_parts[1])
        return (search_location, "")

    def enrich_with_details(self, results, max_enrich=None):
        """
        Click into each listing to get website and phone.
        This is slower but gets data that card view doesn't show.
        """
        count = 0
        total = max_enrich or len(results)

        for result in results:
            if result.get("website"):
                continue
            if not result.get("google_maps_url"):
                continue
            if max_enrich and count >= max_enrich:
                break

            count += 1
            name = result["business_name"][:35]
            print(f"    [{count}/{total}] Enriching: {name}...", end=" ", flush=True)

            try:
                self._page.goto(result["google_maps_url"], wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)

                # Extract website
                website_el = self._page.query_selector('a[data-item-id="authority"]')
                if website_el:
                    result["website"] = website_el.get_attribute("href") or ""

                # Extract phone if not already found
                if not result.get("phone"):
                    phone_el = self._page.query_selector('button[data-item-id*="phone"]')
                    if phone_el:
                        phone_text = phone_el.get_attribute("aria-label") or ""
                        phone_match = re.search(r'[\+\(]?\d[\d\s\-\(\)]{7,}', phone_text)
                        if phone_match:
                            result["phone"] = phone_match.group(0).strip()

                # Extract address if not already found
                if not result.get("address"):
                    addr_el = self._page.query_selector('button[data-item-id="address"]')
                    if addr_el:
                        result["address"] = addr_el.get_attribute("aria-label") or ""
                        result["address"] = result["address"].replace("Address: ", "")

                # Extract category if not already found
                if not result.get("business_category"):
                    cat_el = self._page.query_selector('button[jsaction*="category"]')
                    if cat_el:
                        result["business_category"] = cat_el.inner_text().strip()

                status = []
                if result.get("website"):
                    status.append(f"web: {result['website'][:40]}")
                if result.get("phone"):
                    status.append(f"ph: {result['phone']}")
                print(f"-> {', '.join(status) if status else 'no new data'}")

            except PlaywrightTimeout:
                print("-> timeout")
            except Exception as e:
                print(f"-> error: {str(e)[:50]}")

            time.sleep(1.5)

        return results

    def close(self):
        """Clean up browser resources."""
        try:
            self._page.close()
            self._context.close()
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass
