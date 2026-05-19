"""
Find existing 1st-degree LinkedIn connections in the print/promo industry.

Searches Prakash's connections filtered by print/promo keywords, captures
enough profile context to write personalized DMs, outputs to JSON.

Usage:
    python -m linkedin_automation.find_connections [--limit 20] [--output /tmp/connections.json]

Output JSON shape:
    [
        {
            "name": "Sharon Bates",
            "url": "https://www.linkedin.com/in/sharon-bates-123/",
            "title": "Owner at Keynote Marketing",
            "company": "Keynote Marketing",
            "location": "Dublin, Ireland",
            "about_snippet": "...",
            "recent_post_snippet": "...",
            "mutual_count": 3,
            "is_premium": false,
            "profile_snapshot": "..."   # full page text for Claude to read
        },
        ...
    ]
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import human
from .browser import Browser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search queries - we run multiple to get a good cross-section
# ---------------------------------------------------------------------------

SEARCH_QUERIES = [
    "print promotional products",
    "print shop owner",
    "promotional merchandise",
    "branded merchandise",
    "embroidery apparel print",
    "screen printing",
    "print promo distributor",
]

# Keywords in title/about that indicate print/promo industry
PRINT_PROMO_KEYWORDS = {
    "print", "promo", "promotional", "merchandise", "branded", "embroidery",
    "screen print", "apparel", "workwear", "signage", "gifting", "gifting",
    "corporate gifts", "branded products", "print shop", "print house",
    "distributor", "supplier", "decoration", "imprint", "garment",
}

# Titles that indicate decision-maker / owner (worth DMing)
TARGET_TITLES = {
    "owner", "director", "founder", "managing director", "md", "ceo",
    "head", "manager", "partner", "principal",
}


@dataclass
class ConnectionCandidate:
    name: str
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    about_snippet: str = ""
    recent_post_snippet: str = ""
    mutual_count: int = 0
    is_premium: bool = False
    relevance_score: int = 0
    profile_snapshot: str = ""


def _score_candidate(c: ConnectionCandidate) -> int:
    """Score a candidate by relevance to print/promo. Higher = more relevant."""
    score = 0
    text = f"{c.title} {c.company} {c.about_snippet}".lower()

    for kw in PRINT_PROMO_KEYWORDS:
        if kw in text:
            score += 2

    title_lower = c.title.lower()
    for t in TARGET_TITLES:
        if t in title_lower:
            score += 3
            break

    if c.mutual_count > 0:
        score += min(c.mutual_count, 5)

    return score


def _search_1st_degree_connections(br: Browser, query: str, limit: int = 20) -> list[dict]:
    """
    Search LinkedIn for 1st-degree connections matching the query.
    Returns list of {name, url, title} dicts.
    """
    results = []
    encoded = query.replace(" ", "%20")
    url = f"https://www.linkedin.com/search/results/people/?keywords={encoded}&network=%5B%22F%22%5D"

    br.driver.get(url)
    human.page_load_pause()
    human.random_scroll(br.driver)

    # Wait for any /in/ profile links - more resilient than waiting for a specific container
    try:
        WebDriverWait(br.driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/in/']"))
        )
    except TimeoutException:
        logger.warning(f"No results for query: {query}")
        return []

    # Broader anchor selection - catch all current LinkedIn result link formats
    anchors = br.driver.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")

    seen_urls = set()
    for anchor in anchors[:limit]:
        try:
            href = anchor.get_attribute("href") or ""
            # Normalise: strip query params, keep /in/slug/
            m = re.match(r"(https://www\.linkedin\.com/in/[^/?#]+)", href)
            if not m:
                continue
            profile_url = m.group(1)
            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)

            # Get name from span[aria-hidden='true'] inside anchor
            name = ""
            for span_sel in ["span[aria-hidden='true']", "span"]:
                try:
                    sp = anchor.find_element(By.CSS_SELECTOR, span_sel)
                    candidate = (sp.text or "").strip()
                    if candidate and 2 <= len(candidate) <= 60 and "\n" not in candidate:
                        name = candidate
                        break
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            if not name:
                name = (anchor.text or "").strip().split("\n")[0]

            # Get title from nearby element
            title = ""
            try:
                # Walk up to find the result card
                card = anchor
                for _ in range(5):
                    card = card.find_element(By.XPATH, "..")
                    card_cls = card.get_attribute("class") or ""
                    if "entity-result" in card_cls or "search-result" in card_cls:
                        break
                # Find subtitle/title within card
                for sel in [
                    ".entity-result__primary-subtitle",
                    ".entity-result__secondary-subtitle",
                    "[data-anonymize='job-title']",
                ]:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, sel)
                        title = (el.text or "").strip()
                        if title:
                            break
                    except NoSuchElementException:
                        continue
            except Exception:
                pass

            if name and len(name) > 2:
                results.append({"name": name, "url": profile_url, "title": title})
                logger.info(f"  Found: {name} — {title} ({profile_url})")

        except (StaleElementReferenceException, Exception):
            continue

    return results


def _visit_profile(br: Browser, candidate: ConnectionCandidate) -> None:
    """
    Visit the profile page and enrich the candidate with about text, recent post, etc.
    Modifies candidate in-place.
    """
    br.driver.get(candidate.url)
    human.page_load_pause()
    human.random_scroll(br.driver)
    human.short_pause()

    try:
        page_text = br.driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        page_text = ""

    candidate.profile_snapshot = page_text[:4000]  # cap for Claude

    # Title / headline from h1 + subtitle
    try:
        h1 = br.driver.find_element(By.CSS_SELECTOR, "h1")
        candidate.name = (h1.text or candidate.name).strip()
    except NoSuchElementException:
        pass

    try:
        headline = br.driver.find_element(By.CSS_SELECTOR, ".text-body-medium.break-words")
        candidate.title = (headline.text or candidate.title).strip()
    except NoSuchElementException:
        pass

    # Location
    try:
        loc = br.driver.find_element(By.CSS_SELECTOR, "span.text-body-small.inline.t-black--light.break-words")
        candidate.location = (loc.text or "").strip()
    except NoSuchElementException:
        pass

    # Company (from top experience card)
    try:
        for el in br.driver.find_elements(By.CSS_SELECTOR, "span[aria-hidden='true']"):
            txt = (el.text or "").strip()
            if txt and txt != candidate.name and len(txt) > 2 and len(txt) < 100:
                candidate.company = txt
                break
    except Exception:
        pass

    # About section
    try:
        about_el = br.driver.find_element(By.CSS_SELECTOR, "div.display-flex.ph5.pv3")
        about_text = (about_el.text or "").strip()
        candidate.about_snippet = about_text[:400]
    except NoSuchElementException:
        pass

    if not candidate.about_snippet:
        try:
            for el in br.driver.find_elements(By.CSS_SELECTOR, "section.artdeco-card"):
                txt = (el.text or "").strip()
                if "About" in txt[:20]:
                    lines = [l.strip() for l in txt.split("\n") if l.strip() and l.strip() != "About"]
                    candidate.about_snippet = " ".join(lines)[:400]
                    break
        except Exception:
            pass

    # Mutual connections count
    try:
        for el in br.driver.find_elements(By.CSS_SELECTOR, "span.dist-value, span[data-test-mutual-connections]"):
            txt = (el.text or "").strip()
            m = re.search(r"(\d+)\s*mutual", txt, re.IGNORECASE)
            if m:
                candidate.mutual_count = int(m.group(1))
                break
    except Exception:
        pass

    # Premium badge
    try:
        br.driver.find_element(By.CSS_SELECTOR, "li-icon[type='linkedin-premium']")
        candidate.is_premium = True
    except NoSuchElementException:
        pass

    # Recent post snippet (from activity section)
    try:
        br.driver.get(candidate.url + "recent-activity/all/")
        human.sleep_range(2.0, 4.0)
        posts = br.driver.find_elements(By.CSS_SELECTOR, "span.break-words")
        for p in posts[:5]:
            txt = (p.text or "").strip()
            if len(txt) > 40:
                candidate.recent_post_snippet = txt[:300]
                break
    except Exception:
        pass


def find_print_promo_connections(
    limit: int = 20,
    output_path: Optional[Path] = None,
) -> list[ConnectionCandidate]:
    """
    Main entry point. Returns a ranked list of 1st-degree LinkedIn connections
    in the print/promo industry with enough context to write personalized DMs.
    """
    if output_path is None:
        output_path = Path("/tmp/linkedin_print_connections.json")

    all_candidates: dict[str, ConnectionCandidate] = {}  # url -> candidate

    with Browser() as br:
        if not br.is_logged_in():
            logger.error("Not logged in. Run: python -m linkedin_automation.cli login")
            return []

        # Phase 1: Search across multiple queries, collect unique candidates
        logger.info("Phase 1: Searching connections by keyword...")
        for query in SEARCH_QUERIES:
            logger.info(f"  Searching: '{query}'")
            results = _search_1st_degree_connections(br, query, limit=15)
            for r in results:
                if r["url"] not in all_candidates:
                    all_candidates[r["url"]] = ConnectionCandidate(
                        name=r["name"],
                        url=r["url"],
                        title=r["title"],
                    )
            human.sleep_range(3.0, 6.0)

        logger.info(f"Phase 1 complete: {len(all_candidates)} unique candidates found")

        # Phase 2: Pre-score from title alone to prioritise profile visits
        for c in all_candidates.values():
            c.relevance_score = _score_candidate(c)

        # Sort by pre-score, visit top N profiles only
        ranked = sorted(all_candidates.values(), key=lambda c: c.relevance_score, reverse=True)
        to_enrich = [c for c in ranked if c.relevance_score >= 2][:limit]

        logger.info(f"Phase 2: Enriching top {len(to_enrich)} candidates...")
        for i, candidate in enumerate(to_enrich, 1):
            logger.info(f"  [{i}/{len(to_enrich)}] Visiting: {candidate.name} ({candidate.url})")
            _visit_profile(br, candidate)
            candidate.relevance_score = _score_candidate(candidate)  # re-score with full data
            if i < len(to_enrich):
                human.sleep_range(4.0, 8.0)

    # Final rank and filter
    final = sorted(to_enrich, key=lambda c: c.relevance_score, reverse=True)
    top = [c for c in final if c.relevance_score >= 4][:limit]

    # Serialise to JSON
    output = []
    for c in top:
        output.append({
            "name": c.name,
            "url": c.url,
            "title": c.title,
            "company": c.company,
            "location": c.location,
            "about_snippet": c.about_snippet,
            "recent_post_snippet": c.recent_post_snippet,
            "mutual_count": c.mutual_count,
            "is_premium": c.is_premium,
            "relevance_score": c.relevance_score,
            "profile_snapshot": c.profile_snapshot,
        })

    output_path.write_text(json.dumps(output, indent=2))
    logger.info(f"Saved {len(output)} candidates to {output_path}")

    return top


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Find 1st-degree LinkedIn connections in print/promo")
    parser.add_argument("--limit", type=int, default=20, help="Max candidates to return")
    parser.add_argument("--output", type=Path, default=Path("/tmp/linkedin_print_connections.json"))
    args = parser.parse_args()

    results = find_print_promo_connections(limit=args.limit, output_path=args.output)
    print(f"\n{'='*60}")
    print(f"Found {len(results)} print/promo connections")
    print(f"{'='*60}")
    for i, c in enumerate(results, 1):
        print(f"\n{i}. {c.name}")
        print(f"   Title:    {c.title}")
        print(f"   Company:  {c.company}")
        print(f"   Location: {c.location}")
        print(f"   Score:    {c.relevance_score}")
        if c.about_snippet:
            print(f"   About:    {c.about_snippet[:120]}...")
    print(f"\nFull data saved to: {args.output}")
