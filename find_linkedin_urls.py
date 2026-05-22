#!/usr/bin/env python3
"""
Find LinkedIn URLs for Irish print shops using Google Search.
Safe approach - uses public Google search, no LinkedIn automation.
"""

import csv
import time
import urllib.parse
from typing import Optional
import requests
from bs4 import BeautifulSoup
import sys

# Headers to avoid being blocked
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def google_search_linkedin(company_name: str, city: str = "", max_results: int = 5) -> Optional[str]:
    """
    Search Google for LinkedIn URL of a company.
    Returns the first LinkedIn URL found or None.
    """
    query = f'site:linkedin.com "{company_name}"'
    if city and city.strip():
        query += f' "{city}"'

    try:
        # Using DuckDuckGo API (no auth required, friendly to automation)
        search_url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}"

        response = requests.get(search_url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find LinkedIn links
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if 'linkedin.com' in href and '/company/' in href:
                # Extract actual URL from DuckDuckGo redirect
                if href.startswith('/l/?'):
                    # Parse DuckDuckGo redirect
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(href)
                    params = parse_qs(parsed.query)
                    if 'uddg' in params:
                        return params['uddg'][0]
                return href

        return None

    except Exception as e:
        print(f"Error searching for {company_name}: {e}", file=sys.stderr)
        return None


def process_csv(input_file: str, output_file: str):
    """
    Read CSV, search for LinkedIn URLs, write results.
    """
    results = []
    total = 0
    found = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            total += 1
            business_name = row.get('business_name', '').strip()
            city = row.get('city', '').strip()

            if not business_name:
                print(f"Skipping row {total}: no business name")
                results.append({**row, 'linkedin_url': ''})
                continue

            print(f"[{total}] Searching for: {business_name} ({city})...", end=' ', flush=True)

            # Search with retry
            linkedin_url = google_search_linkedin(business_name, city)

            if linkedin_url:
                found += 1
                print(f"✓ Found")
                results.append({**row, 'linkedin_url': linkedin_url})
            else:
                print(f"✗ Not found")
                results.append({**row, 'linkedin_url': ''})

            # Rate limiting - be respectful to search engines
            time.sleep(2)

    # Write results
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        fieldnames = list(results[0].keys()) if results else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✓ Processed {total} shops, found {found} LinkedIn URLs ({found*100//total}%)")
    print(f"Results saved to: {output_file}")


if __name__ == '__main__':
    input_csv = '/tmp/irish_print_shops.csv'
    output_csv = '/tmp/irish_print_shops_with_linkedin.csv'

    print(f"Finding LinkedIn URLs for Irish print shops...")
    print(f"Input:  {input_csv}")
    print(f"Output: {output_csv}\n")

    process_csv(input_csv, output_csv)
