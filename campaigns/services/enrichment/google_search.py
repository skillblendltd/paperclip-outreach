"""
Google Custom Search enricher.
Finds LinkedIn profile URLs and decision-maker names via Google search.
Free tier: 100 queries per day.
Setup: https://programmablesearchengine.google.com/
"""

import logging
import re
import requests

logger = logging.getLogger(__name__)

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


def search_linkedin_profile(api_key, cse_id, person_name, company_name):
    """
    Search Google for a person's LinkedIn profile.
    Returns LinkedIn URL or None.
    """
    query = f'"{person_name}" "{company_name}" site:linkedin.com/in'

    try:
        resp = requests.get(
            GOOGLE_CSE_URL,
            params={
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": 3,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Google CSE failed (%s): %s", resp.status_code, query)
            return None

        items = resp.json().get("items", [])
        for item in items:
            link = item.get("link", "")
            if "linkedin.com/in/" in link:
                return link

    except requests.RequestException as e:
        logger.error("Google CSE error: %s", e)

    return None


def search_decision_maker(api_key, cse_id, company_name, city=""):
    """
    Search Google for the owner/director of a company.
    Returns dict {name, title, linkedin_url} or None.
    """
    location = f' "{city}"' if city else ""
    query = f'"{company_name}"{location} owner OR director OR founder OR "managing director"'

    try:
        resp = requests.get(
            GOOGLE_CSE_URL,
            params={
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": 5,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Google CSE failed (%s): %s", resp.status_code, query)
            return None

        items = resp.json().get("items", [])
        linkedin_url = None

        for item in items:
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            title_text = item.get("title", "")

            # Check for LinkedIn profile
            if "linkedin.com/in/" in link:
                linkedin_url = link
                # Try to extract name from LinkedIn title: "John Murphy - Owner - Company | LinkedIn"
                li_name_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[-|]', title_text)
                if li_name_match:
                    name = li_name_match.group(1)
                    # Extract title from the middle part
                    parts = re.split(r'\s*[-|]\s*', title_text)
                    role = parts[1] if len(parts) > 2 else "Owner"
                    return {
                        "name": name,
                        "title": role,
                        "linkedin_url": linkedin_url,
                        "source": "google",
                    }

            # Check snippet for owner mentions
            name_patterns = [
                re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*(?:is|,)\s*(?:the\s+)?(?:owner|founder|director|MD)', re.IGNORECASE),
                re.compile(r'(?:owner|founder|director|MD)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})', re.IGNORECASE),
            ]
            for pattern in name_patterns:
                match = pattern.search(snippet)
                if match:
                    return {
                        "name": match.group(1),
                        "title": "Owner",
                        "linkedin_url": linkedin_url,
                        "source": "google",
                    }

    except requests.RequestException as e:
        logger.error("Google CSE error: %s", e)

    return None
