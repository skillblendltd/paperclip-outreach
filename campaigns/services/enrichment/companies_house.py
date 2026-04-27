"""
UK Companies House enricher.
Scrapes the free GOV.UK web interface - no API key required.
Rate limit: be gentle, ~1 request per second.
"""

import logging
import re
import time
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://find-and-update.company-information.service.gov.uk"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _title_case_name(name_str):
    """Convert 'BOURNE, Anthony' to 'Anthony Bourne'."""
    if not name_str:
        return ""
    name_str = name_str.strip()
    if "," in name_str:
        parts = name_str.split(",", 1)
        surname = parts[0].strip().title()
        forenames = parts[1].strip().title()
        first_name = forenames.split()[0] if forenames else ""
        return f"{first_name} {surname}".strip()
    return name_str.title()


def _normalize(name):
    """Normalize company name for comparison."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in ["ltd", "ltd.", "limited", "plc", "llp", "inc", "co.", "co"]:
        name = name.replace(suffix, "")
    # Remove punctuation and extra spaces
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _name_similarity(name1, name2):
    """Simple word overlap similarity between two company names."""
    words1 = set(_normalize(name1).split())
    words2 = set(_normalize(name2).split())
    if not words1 or not words2:
        return 0.0
    overlap = words1 & words2
    return len(overlap) / max(len(words1), len(words2))


def search_company(company_name):
    """
    Search Companies House web for a company by name.
    Returns the first matching company number, or None.
    Validates name similarity to avoid false positives.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/search/companies",
            params={"q": company_name},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        # Extract company numbers from search results
        numbers = re.findall(r'/company/([A-Z0-9]+)', resp.text)
        if not numbers:
            return None

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for n in numbers:
            if n not in seen:
                seen.add(n)
                unique.append(n)

        # Return first unique match (most relevant by Companies House ranking)
        return unique[0] if unique else None

    except requests.RequestException as e:
        logger.error("CH search error for %s: %s", company_name, e)
        return None


def get_directors(company_number):
    """
    Get active directors from the company officers page.
    Returns list of dicts: [{name, role}, ...]
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/company/{company_number}/officers",
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        html = resp.text
        directors = []

        # Pattern: <a class="govuk-link" href="/officers/xxx/appointments">SURNAME, Firstname</a>
        # followed by role info in <dd id="officer-role-N">
        name_pattern = re.compile(
            r'<span id="officer-name-(\d+)">\s*'
            r'<a[^>]+>([^<]+)</a>',
            re.DOTALL,
        )
        role_pattern = re.compile(
            r'<dd id="officer-role-(\d+)"[^>]*>\s*([^<]+)',
            re.DOTALL,
        )
        status_pattern = re.compile(
            r'<span id="officer-status-tag-(\d+)"[^>]*>([^<]+)</span>',
        )

        # Extract names
        names = {}
        for match in name_pattern.finditer(html):
            idx = match.group(1)
            raw_name = match.group(2).strip()
            names[idx] = raw_name

        # Extract roles
        roles = {}
        for match in role_pattern.finditer(html):
            idx = match.group(1)
            role = match.group(2).strip()
            roles[idx] = role

        # Extract statuses
        statuses = {}
        for match in status_pattern.finditer(html):
            idx = match.group(1)
            status = match.group(2).strip().lower()
            statuses[idx] = status

        # Combine - only active officers with director roles
        for idx, raw_name in names.items():
            status = statuses.get(idx, "")
            if status != "active":
                continue
            role = roles.get(idx, "Director")
            if "director" in role.lower() or "secretary" in role.lower():
                directors.append({
                    "name": _title_case_name(raw_name),
                    "role": role,
                })

        # If no directors found with role filter, take first active officer
        if not directors:
            for idx, raw_name in names.items():
                if statuses.get(idx, "") == "active":
                    directors.append({
                        "name": _title_case_name(raw_name),
                        "role": roles.get(idx, "Director"),
                    })
                    break

        return directors

    except requests.RequestException as e:
        logger.error("CH officers error for %s: %s", company_number, e)
        return []


def enrich_prospect(business_name, city=""):
    """
    Main entry point: look up a business and return the primary director.
    Returns dict {name, title, source} or None.
    """
    # Search with city hint for better matching
    search_term = f"{business_name} {city}".strip() if city else business_name
    company_number = search_company(search_term)

    if not company_number:
        # Try without city
        if city:
            company_number = search_company(business_name)
        if not company_number:
            return None

    time.sleep(0.5)

    directors = get_directors(company_number)
    if not directors:
        return None

    # Skip corporate directors (company names acting as directors)
    corporate_words = {"limited", "ltd", "llp", "plc", "services", "group", "management", "holdings"}
    for director in directors:
        name = director["name"]
        name_lower = name.lower()
        if any(w in name_lower for w in corporate_words):
            continue
        # Must have at least a first and last name
        if " " not in name.strip():
            continue
        return {
            "name": name,
            "title": director["role"],
            "source": "companies_house",
        }

    return None
