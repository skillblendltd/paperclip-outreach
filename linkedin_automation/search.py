"""
LinkedIn discovery module.

Given a CSV row (business name, city, country, website), find:
1. The LinkedIn company page (with website-domain verification)
2. The most senior decision-maker (owner/CEO/founder)

Phase 1 of the pipeline. Read-only operations, lower risk profile
than connection requests.

Strategy:
1. Search LinkedIn company search with country geo filter (eliminates cross-country FPs)
2. Score top N candidates by name similarity + city + token overlap
3. For each candidate above MATCH_MIN_VERIFY_SCORE, load /about/ and compare website
4. Domain match (+20) is the dominant signal - eliminates name-collision FPs
5. Top-scoring candidate after verification wins
6. From the company page, hit /people, score employees by title seniority
7. Return highest-scoring decision-maker

Failure modes:
- No company found at all → mark not_found
- All candidates fail website verification → mark needs_review (score 3-12 zone)
- Company found but no public employees → mark not_found
- LinkedIn block detected → mark blocked (circuit breaker)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urlparse

from . import config, human

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .browser import Browser

logger = logging.getLogger(__name__)


@dataclass
class CompanyCandidate:
    url: str
    handle: str
    label: str        # The text LinkedIn showed for this result
    score: int
    verified_domain: bool = False
    verified_website: str = ""


@dataclass
class DiscoveryResult:
    """Outcome of one discovery attempt."""
    status: str  # 'done' | 'not_found' | 'needs_review' | 'blocked' | 'error'
    company_url: str = ""
    company_id: str = ""
    person_url: str = ""
    person_name: str = ""
    person_title: str = ""
    match_score: int = 0
    domain_verified: bool = False
    error: str = ""
    candidates_considered: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def _clean_person_name(name: str) -> str:
    """Strip LinkedIn UI chrome from a person's name. e.g. 'Frank Hanley • 2nd' → 'Frank Hanley'"""
    # Remove trailing connection degree indicator: " • 2nd", " · 3rd", "• 1st" etc.
    return re.sub(r"\s*[•·]\s*\d+(st|nd|rd|th).*$", "", name).strip()


_CONNECTION_DEGREE_RE = re.compile(r"^[•·]?\s*\d+(st|nd|rd|th)\s*$")


def _extract_domain(url: str) -> str:
    """
    Extract the registrable domain from a URL.

    Examples:
        https://www.tpi.ie/         → tpi.ie
        http://brandit.ie/about     → brandit.ie
        www.example.co.uk           → example.co.uk
        not-a-url                   → ""
    """
    if not url:
        return ""
    s = url.strip().lower()
    # Add scheme if missing so urlparse works
    if not s.startswith(("http://", "https://")):
        s = "http://" + s
    try:
        netloc = urlparse(s).netloc
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Drop port if any
    netloc = netloc.split(":")[0]
    return netloc


def _domains_match(a: str, b: str) -> bool:
    """Two domains match if they're equal OR one is a subdomain of the other."""
    a, b = a.lower(), b.lower()
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow subdomain relationships - e.g., shop.tpi.ie ↔ tpi.ie
    return a.endswith("." + b) or b.endswith("." + a)


# ---------------------------------------------------------------------------
# Company search (with country geo filter)
# ---------------------------------------------------------------------------

def _company_search_url(business_name: str, country_code: str = "") -> str:
    """
    LinkedIn company search URL.

    NOTE: geo filter is DISABLED. The companyHqGeo URL parameter has proven
    unreliable - it returns zero results for valid Irish companies that have
    LinkedIn presence. The matcher relies on name+city+website-domain
    scoring to filter cross-country false positives at the candidate-scoring
    stage instead.

    To re-enable for testing, set DISCOVERY_USE_GEO_FILTER=True in config.
    """
    keywords = quote_plus(business_name)
    base = f"https://www.linkedin.com/search/results/companies/?keywords={keywords}"

    if getattr(config, "DISCOVERY_USE_GEO_FILTER", False):
        geo_urn = config.COUNTRY_GEO_URN.get(country_code.upper())
        if geo_urn:
            base += f"&companyHqGeo=%5B%22{geo_urn}%22%5D"
    return base


def _collect_candidates(br: Browser, business_name: str, city: str) -> list[CompanyCandidate]:
    """
    Walk the LinkedIn company search results and score every plausible match.

    Returns top candidates sorted by score (best first). Does NOT yet
    verify website domain - that's a separate, more expensive step.
    """
    target_name = _normalize(business_name)
    target_city = _normalize(city)

    try:
        WebDriverWait(br.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/company/']"))
        )
    except TimeoutException:
        return []

    anchors = br.driver.find_elements(By.CSS_SELECTOR, "a[href*='/company/']")

    candidates: dict[str, CompanyCandidate] = {}

    for anchor in anchors[:30]:
        try:
            href = anchor.get_attribute("href") or ""
            text = (anchor.text or "").strip()
            if not href or "/company/" not in href:
                continue
            if "/search/" in href or "/feed/" in href:
                continue
            if not text:
                continue

            m = re.search(r"linkedin\.com/company/([^/?#]+)", href)
            if not m:
                continue
            handle = m.group(1)
            canonical_url = f"https://www.linkedin.com/company/{handle}/"

            # Each handle should only appear once - keep the highest-scoring instance
            text_norm = _normalize(text.split("\n")[0])  # First line is the company name
            score = 0

            if text_norm == target_name:
                score += 10
            elif target_name in text_norm or text_norm in target_name:
                score += 5
            else:
                target_tokens = set(target_name.split()) - config.COMPANY_NAME_STOPWORDS
                text_tokens = set(text_norm.split()) - config.COMPANY_NAME_STOPWORDS
                overlap = target_tokens & text_tokens
                if overlap:
                    score += len(overlap)

            # City present in card text (subtitle usually shows location)
            full_card_text = _normalize(text)
            if target_city and target_city in full_card_text:
                score += 2

            existing = candidates.get(handle)
            if existing is None or score > existing.score:
                candidates[handle] = CompanyCandidate(
                    url=canonical_url,
                    handle=handle,
                    label=text.split("\n")[0],
                    score=score,
                )

        except StaleElementReferenceException:
            continue

    # Sort by score descending, keep top N
    ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
    return ranked[:config.MATCH_CANDIDATE_LIMIT]


# ---------------------------------------------------------------------------
# Website verification (load /about/ and compare domain)
# ---------------------------------------------------------------------------

def _extract_website_from_about_page(br: Browser, company_url: str) -> str:
    """
    Load the company About page and pull out the website URL.

    LinkedIn renders the website as an <a> tag in the About section.
    Returns the raw href (or empty string if not found).
    """
    about_url = company_url.rstrip("/") + "/about/"
    br.driver.get(about_url)
    human.page_load_pause()
    human.random_scroll(br.driver)

    blocked, reason = br.is_blocked()
    if blocked:
        raise RuntimeError(f"LinkedIn block detected: {reason}")

    # Multiple selector strategies, in order of stability:
    selectors = [
        # 1. The dt/dd "Website" label pattern (most stable)
        "dl a[href^='http']:not([href*='linkedin.com'])",
        # 2. Any external link in the About section
        "section a[href^='http']:not([href*='linkedin.com'])",
        # 3. Anchors whose text looks like a domain
        "a[href*='://'][target='_blank']",
    ]

    for sel in selectors:
        try:
            elements = br.driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements[:5]:
                href = (el.get_attribute("href") or "").strip()
                if not href or "linkedin.com" in href:
                    continue
                # LinkedIn wraps external links in a redirector - extract real URL
                # e.g. https://www.linkedin.com/redir/redirect?url=...
                if "linkedin.com/redir" in href:
                    m = re.search(r"url=([^&]+)", href)
                    if m:
                        from urllib.parse import unquote
                        href = unquote(m.group(1))
                # Looks like an external website URL
                if href.startswith(("http://", "https://")):
                    return href
        except StaleElementReferenceException:
            continue

    return ""


def _verify_candidate(br: Browser, candidate: CompanyCandidate, csv_domain: str) -> bool:
    """
    Load the candidate's /about/ page and check if its website matches our CSV.

    Returns True if domains match (and updates candidate.verified_domain=True),
    False otherwise.

    Side effects: navigates the browser to the company About page.
    """
    if not csv_domain:
        return False

    listed_url = _extract_website_from_about_page(br, candidate.url)
    listed_domain = _extract_domain(listed_url)
    candidate.verified_website = listed_url

    if _domains_match(csv_domain, listed_domain):
        candidate.verified_domain = True
        candidate.score += config.MATCH_DOMAIN_BONUS
        logger.info(
            f"Domain match: {candidate.handle} listed={listed_domain} csv={csv_domain}"
        )
        return True
    return False


# ---------------------------------------------------------------------------
# Decision-maker selection (unchanged from v1)
# ---------------------------------------------------------------------------

def _score_title(title: str) -> int:
    """Higher score = more senior. 0 = skip this person."""
    t = (title or "").lower()
    for pattern in config.SKIP_TITLE_PATTERNS:
        if pattern in t:
            return 0
    for i, keyword in enumerate(config.DECISION_MAKER_TITLE_PRIORITY):
        if keyword in t:
            return len(config.DECISION_MAKER_TITLE_PRIORITY) - i
    return 0


def _people_tab_is_empty(driver) -> bool:
    """
    Detect LinkedIn's '0 associated members' empty state on a company People tab.

    Small businesses often have 0 employees who've formally linked themselves
    to the company page on LinkedIn - even when the owner uses LinkedIn
    personally. In that case, we should fall back to people-search.
    """
    try:
        page = (driver.page_source or "")[:50000].lower()
        if "0 associated members" in page:
            return True
        if "did not return any results" in page:
            return True
        # Generic "no results" fallback
        if "no results found" in page and "/people" in driver.current_url:
            return True
    except Exception:
        pass
    return False


def _find_decision_maker(br: Browser, company_url: str) -> Optional[dict]:
    """
    Visit company's People tab, find the highest-scoring decision-maker.

    Strategy: load /people/, scroll aggressively to trigger lazy-loaded
    employee cards, try multiple selectors to find profile links.

    Returns None if no employees are listed - caller should fall back to
    people-search via business name.
    """
    people_url = company_url.rstrip("/") + "/people/"
    br.driver.get(people_url)
    human.page_load_pause()

    blocked, reason = br.is_blocked()
    if blocked:
        raise RuntimeError(f"LinkedIn block detected: {reason}")

    # Early exit on '0 associated members' - no point scrolling.
    if _people_tab_is_empty(br.driver):
        logger.info(f"People tab is empty for {company_url} - will try fallback search.")
        return None

    # Aggressive scrolling - LinkedIn lazy-loads employee cards on scroll
    for _ in range(4):
        br.driver.execute_script("window.scrollBy(0, 800)")
        human.short_pause()
    human.sleep_range(1.5, 3.0)

    # Try multiple selector strategies for /in/ profile links
    # LinkedIn uses different anchor patterns in different page layouts
    selectors_to_try = [
        "a[href*='/in/'][data-test-app-aware-link]",  # New layout
        "a[href*='/in/'].app-aware-link",
        "a[href*='linkedin.com/in/']",
        "a[href*='/in/']",  # Fallback - any /in/ link
    ]

    anchors = []
    for sel in selectors_to_try:
        try:
            WebDriverWait(br.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            anchors = br.driver.find_elements(By.CSS_SELECTOR, sel)
            if anchors:
                logger.debug(f"Found {len(anchors)} /in/ anchors with selector: {sel}")
                break
        except TimeoutException:
            continue

    if not anchors:
        # Save the People page so we can inspect what LinkedIn actually showed us
        screenshot = br.screenshot(f"people_no_anchors_{company_url.rsplit('/', 2)[-2]}")
        logger.warning(f"No /in/ anchors on {people_url}. Screenshot: {screenshot}")
        return None

    candidates: list[dict] = []
    seen_urls = set()

    for anchor in anchors[:30]:
        try:
            href = anchor.get_attribute("href") or ""
            if not href or "/in/" not in href:
                continue
            m = re.search(r"linkedin\.com/in/([^/?#]+)", href)
            if not m:
                continue
            person_url = f"https://www.linkedin.com/in/{m.group(1)}/"
            if person_url in seen_urls:
                continue
            seen_urls.add(person_url)

            container = anchor
            for _ in range(4):
                try:
                    container = container.find_element(By.XPATH, "..")
                except NoSuchElementException:
                    break
            card_text = (container.text or "").strip()
            name = _clean_person_name((anchor.text or "").strip().split("\n")[0])

            title = ""
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]
            for line in lines:
                if _clean_person_name(line) == name:
                    continue
                if line.lower() in ("connect", "follow", "message", "view profile"):
                    continue
                if "degree connection" in line.lower() or "see more" in line.lower():
                    continue
                if _CONNECTION_DEGREE_RE.match(line.strip()):
                    continue
                title = line
                break

            score = _score_title(title)
            if score == 0:
                continue

            candidates.append({
                "person_url": person_url,
                "person_name": name,
                "person_title": title,
                "score": score,
            })
        except StaleElementReferenceException:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[0]


def _find_decision_maker_via_people_search(
    br: Browser,
    business_name: str,
    city: str,
) -> Optional[dict]:
    """
    Fallback for companies with 0 associated members on LinkedIn.

    Runs a people-search keyed on the business name. Common pattern for small
    businesses: owner writes 'Owner at Brandit Promotional Products' in their
    headline but never formally links to the company page. This catches them.

    Scoring:
      +10 business_name appears in the result's headline text
      +5  business_name appears anywhere in the result card
      +3  city appears in the result card
      +1-13 senior title score from _score_title

    Returns the highest-scoring person, or None.
    """
    keywords = quote_plus(business_name)
    url = f"https://www.linkedin.com/search/results/people/?keywords={keywords}"
    br.driver.get(url)
    human.page_load_pause()
    human.random_scroll(br.driver)
    human.short_pause()

    blocked, reason = br.is_blocked()
    if blocked:
        raise RuntimeError(f"LinkedIn block detected: {reason}")

    try:
        WebDriverWait(br.driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/in/']"))
        )
    except TimeoutException:
        return None

    target_business = _normalize(business_name)
    target_city = _normalize(city)

    candidates: list[dict] = []
    seen_urls = set()

    anchors = br.driver.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")

    for anchor in anchors[:25]:
        try:
            href = anchor.get_attribute("href") or ""
            if not href or "/in/" not in href:
                continue
            m = re.search(r"linkedin\.com/in/([^/?#]+)", href)
            if not m:
                continue
            person_url = f"https://www.linkedin.com/in/{m.group(1)}/"
            if person_url in seen_urls:
                continue
            seen_urls.add(person_url)

            # --- Name: always from inside the anchor, never from container ---
            # Walking up 5 levels can reach a container spanning multiple result
            # cards, causing content_lines[0] to grab a neighbor's name.
            # LinkedIn puts the display name in span[aria-hidden='true'] inside
            # each profile link. That span is co-located with the href → no mismatch.
            name = ""
            for span_sel in ["span[aria-hidden='true']", "span.visually-hidden ~ span", "span"]:
                try:
                    span = anchor.find_element(By.CSS_SELECTOR, span_sel)
                    candidate = (span.text or "").strip()
                    if candidate and len(candidate) > 2:
                        name = _clean_person_name(candidate)
                        break
                except (NoSuchElementException, StaleElementReferenceException):
                    continue
            if not name:
                name = _clean_person_name((anchor.text or "").strip().split("\n")[0])
            if not name:
                continue  # no name → skip; this is likely a non-profile link

            # --- Headline + card text: walk up 3 levels (safer than 5) ---
            container = anchor
            for _ in range(3):
                try:
                    container = container.find_element(By.XPATH, "..")
                except NoSuchElementException:
                    break
            card_text = (container.text or "").strip()
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]

            def _is_nav(line: str) -> bool:
                l = line.lower()
                if l in ("connect", "follow", "message", "view profile", "connect with"):
                    return True
                if "degree connection" in l:
                    return True
                if "·" in line and " ago" in l:
                    return True
                if _CONNECTION_DEGREE_RE.match(line.strip()):
                    return True
                return False

            content_lines = [l for l in lines if not _is_nav(l) and _clean_person_name(l) != name]
            headline = content_lines[0] if content_lines else ""

            card_text_norm = _normalize(card_text)
            headline_norm = _normalize(headline)

            # Business name must appear in the HEADLINE - not just anywhere in card.
            # card_text includes text from adjacent result cards (container pollution),
            # so a CEO with no connection to the business can still score > 0 via
            # card_text token overlap. Headline is co-located with the anchor so it
            # reliably describes THIS person's current role.
            business_score = 0
            if target_business and target_business in headline_norm:
                business_score = 10
            else:
                target_tokens = set(target_business.split()) - config.COMPANY_NAME_STOPWORDS
                headline_tokens = set(headline_norm.split()) - config.COMPANY_NAME_STOPWORDS
                overlap = target_tokens & headline_tokens
                if overlap:
                    business_score = len(overlap)

            # Hard gate: zero business-name match in headline → skip.
            if business_score == 0:
                continue

            score = business_score
            if target_city and target_city in card_text_norm:
                score += 3

            score += _score_title(headline)

            if score < 5:
                continue

            candidates.append({
                "person_url": person_url,
                "person_name": name,
                "person_title": headline,
                "score": score,
            })

        except StaleElementReferenceException:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[0]
    logger.info(
        f"People-search fallback found: {top['person_name']} - {top['person_title']} "
        f"(score={top['score']})"
    )
    return top


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _sanitize_business_name(name: str) -> str:
    """
    Strip noise from business names before using as a LinkedIn search query.

    Patterns that hurt search accuracy:
    - "We Brand Merchandise | branded pens, caps..." → "We Brand Merchandise"
      (pipe char separates the brand from a tagline/description)
    - "Quest Merchandise - Promotional Products" → "Quest Merchandise"
      (dash separates brand from a generic descriptor)
    - Leading/trailing whitespace after stripping
    """
    # Strip everything from ' | ' onward (tagline separator)
    if " | " in name:
        name = name[:name.index(" | ")]
    # Strip everything from ' - ' onward (descriptor separator)
    # Guard: only strip if the left side is >= 2 words so we don't destroy
    # single-word brand names that happen to contain a dash.
    if " - " in name:
        left = name[:name.index(" - ")]
        if len(left.split()) >= 2:
            name = left
    return name.strip()


def discover_prospect(
    br: Browser,
    business_name: str,
    city: str = "",
    country_code: str = "",
    website: str = "",
) -> DiscoveryResult:
    """
    Find LinkedIn company + decision-maker for one business.

    The matching pipeline:
    1. Search LinkedIn with country geo filter
    2. Score top candidates by name + city + token overlap
    3. If top candidate's score >= MATCH_MIN_AUTO_SCORE → auto-accept
    4. Otherwise, for each candidate above MATCH_MIN_VERIFY_SCORE, load /about/
       and check website domain. Domain match adds +20 (dominant signal).
    5. Pick highest scoring after verification
    6. If still ambiguous (score 3-12, no domain match) → status=needs_review
    """
    try:
        csv_domain = _extract_domain(website)
        search_name = _sanitize_business_name(business_name)

        # ----- Step 1: Search and collect candidates -----
        br.driver.get(_company_search_url(search_name, country_code))
        human.page_load_pause()
        human.random_scroll(br.driver)

        blocked, reason = br.is_blocked()
        if blocked:
            return DiscoveryResult(status="blocked", error=reason)

        candidates = _collect_candidates(br, search_name, city)

        if not candidates:
            return DiscoveryResult(status="not_found", error="no_search_results")

        top = candidates[0]
        # ----- Step 2: Auto-accept if confidence is high enough -----
        if top.score >= config.MATCH_MIN_AUTO_SCORE:
            chosen = top
            logger.info(
                f"Auto-accept '{business_name}' → {chosen.handle} "
                f"(score={chosen.score}, no domain verification needed)"
            )
        else:
            # ----- Step 3: Try to verify the top few candidates via website -----
            verify_pool = [c for c in candidates if c.score >= config.MATCH_MIN_VERIFY_SCORE]
            chosen = None

            if csv_domain and verify_pool:
                # Verify top 3 candidates max - bound page load cost
                for cand in verify_pool[:3]:
                    human.sleep_range(2, 5)  # Small pause between candidate visits
                    if _verify_candidate(br, cand, csv_domain):
                        chosen = cand
                        break  # Domain match is decisive

            # Re-sort the pool by post-verification score, take top
            if chosen is None:
                verify_pool.sort(key=lambda c: c.score, reverse=True)
                if verify_pool and verify_pool[0].score >= config.MATCH_MIN_AUTO_SCORE:
                    chosen = verify_pool[0]
                else:
                    # We have plausible candidates but couldn't verify any.
                    # Don't auto-accept - human review.
                    return DiscoveryResult(
                        status="needs_review",
                        company_url=top.url,
                        match_score=top.score,
                        domain_verified=False,
                        error=f"ambiguous_match (top_score={top.score}, csv_domain={csv_domain or 'none'})",
                        candidates_considered=[
                            {"handle": c.handle, "label": c.label, "score": c.score,
                             "verified_website": c.verified_website}
                            for c in candidates[:5]
                        ],
                    )

        # ----- Step 4: Find decision-maker on the chosen company -----
        human.sleep_range(3, 7)  # Hesitation - human reading the company page

        decision_maker = _find_decision_maker(br, chosen.url)
        decision_maker_source = "company_people_tab"

        # ----- Step 5: Fallback to people-search if company has no employees -----
        # Small businesses often have 0 employees formally linked to the
        # company page. The owner uses LinkedIn but writes the business in
        # their headline rather than associating with the company entity.
        if not decision_maker:
            human.sleep_range(2, 5)
            decision_maker = _find_decision_maker_via_people_search(
                br, business_name, city,
            )
            decision_maker_source = "people_search_fallback"

        if not decision_maker:
            return DiscoveryResult(
                status="not_found",
                company_url=chosen.url,
                match_score=chosen.score,
                domain_verified=chosen.verified_domain,
                error="no_decision_maker_after_fallback",
            )

        result = DiscoveryResult(
            status="done",
            company_url=chosen.url,
            person_url=decision_maker["person_url"],
            person_name=decision_maker["person_name"],
            person_title=decision_maker["person_title"],
            match_score=chosen.score,
            domain_verified=chosen.verified_domain,
        )
        # Track which path found the decision-maker for diagnostics
        result.candidates_considered = [{
            "decision_maker_source": decision_maker_source,
            "person_score": decision_maker.get("score"),
        }]
        return result

    except RuntimeError as e:
        return DiscoveryResult(status="blocked", error=str(e))

    except Exception as e:
        logger.exception(f"Discovery failed for {business_name}")
        return DiscoveryResult(status="error", error=str(e)[:500])
