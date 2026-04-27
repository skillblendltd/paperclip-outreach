"""
Irish Companies Registration Office (CRO) enricher.
Uses the CORE public search at https://core.cro.ie/
Free, no API key required. Playwright-based scraping.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

# CRO search URL
CRO_SEARCH_URL = "https://core.cro.ie/"


def _clean_name(raw_name):
    """Convert CRO-style names to readable format."""
    if not raw_name:
        return ""
    # CRO sometimes shows names as "SURNAME, Firstname" or all caps
    name = raw_name.strip()
    if "," in name:
        parts = name.split(",", 1)
        surname = parts[0].strip().title()
        forenames = parts[1].strip().title()
        first_name = forenames.split()[0] if forenames else ""
        return f"{first_name} {surname}".strip()
    return name.title()


async def search_company_cro(page, company_name):
    """
    Search CRO for a company and return list of directors.
    Uses Playwright page object.
    Returns list of dicts: [{name, title}, ...] or empty list.
    """
    try:
        await page.goto(CRO_SEARCH_URL, timeout=15000)
        await page.wait_for_load_state("networkidle", timeout=10000)

        # Type company name into search
        search_input = page.locator('input[name="CompanyName"], input#CompanyName, input[type="text"]').first
        await search_input.fill(company_name)

        # Click search button
        search_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Search")').first
        await search_btn.click()
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Look for company results - click first active company
        # CRO shows results in a table with company name, number, status
        rows = page.locator("table tbody tr, .search-results a, .company-result")
        count = await rows.count()
        if count == 0:
            return []

        # Click first result to get company details
        first_link = page.locator("table tbody tr a, .search-results a").first
        if await first_link.count() > 0:
            await first_link.click()
            await page.wait_for_load_state("networkidle", timeout=15000)

        # Extract director information from company detail page
        # CRO shows officers in a table or list
        page_text = await page.content()

        directors = _extract_directors_from_html(page_text)
        return directors

    except Exception as e:
        logger.warning("CRO search failed for %s: %s", company_name, e)
        return []


def _extract_directors_from_html(html):
    """Extract director names from CRO company detail page HTML."""
    directors = []

    # Pattern 1: Look for "Director" rows in tables
    # CRO typically shows: Name | Role | Appointed
    director_pattern = re.compile(
        r'(?:Director|Secretary).*?<td[^>]*>\s*([A-Z][A-Za-z\s,\'-]+?)\s*</td>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in director_pattern.finditer(html):
        name = _clean_name(match.group(1))
        if name and len(name) > 3:
            directors.append({"name": name, "title": "Director"})

    # Pattern 2: Look for structured officer data
    officer_pattern = re.compile(
        r'(?:name|officer)["\s:>]+([A-Z][A-Za-z\s,\'-]{3,40}?)(?:</|"|<)',
        re.IGNORECASE,
    )
    if not directors:
        for match in officer_pattern.finditer(html):
            name = _clean_name(match.group(1))
            if name and len(name) > 3 and name.lower() not in ("director", "secretary", "company"):
                directors.append({"name": name, "title": "Director"})
                break  # Take first match only

    return directors


def enrich_prospect_sync(browser, business_name):
    """
    Synchronous wrapper for CRO lookup.
    Pass a Playwright browser instance.
    Returns dict {name, title, source} or None.
    """
    import asyncio

    async def _run():
        context = await browser.new_context()
        page = await context.new_page()
        try:
            directors = await search_company_cro(page, business_name)
            if directors:
                return {
                    "name": directors[0]["name"],
                    "title": directors[0]["title"],
                    "source": "cro",
                }
            return None
        finally:
            await context.close()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context already
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, _run()).result(timeout=30)
        return asyncio.run(_run())
    except Exception as e:
        logger.error("CRO enrichment failed for %s: %s", business_name, e)
        return None
