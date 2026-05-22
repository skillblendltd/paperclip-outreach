#!/usr/bin/env python3
"""
LinkedIn Enrichment for Print & Promo Businesses in Ireland

Adds LinkedIn company URLs to prospect data by:
1. Using website metadata (LinkedIn links in footer/about)
2. Google search for "company name LinkedIn"
3. Direct LinkedIn company search

Run with: python linkedin_enrich.py --input ireland_print_promo.csv --output ireland_print_promo_linkedin.csv
"""

import csv
import json
import time
import argparse
from urllib.parse import urlparse, urljoin
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Optional: BeautifulSoup for scraping, requests for HTTP
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Optional: Playwright for browser-based LinkedIn search
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class LinkedInEnricher:
    def __init__(self, cache_file=None):
        """
        Initialize the enricher with optional caching.

        Args:
            cache_file: JSON file to cache LinkedIn lookups (avoid re-scraping)
        """
        self.cache = {}
        self.cache_file = cache_file or 'linkedin_cache.json'
        self.load_cache()

    def load_cache(self):
        """Load cached LinkedIn URLs from JSON."""
        cache_path = Path(self.cache_file)
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached LinkedIn URLs")
            except Exception as e:
                logger.warning(f"Could not load cache: {e}")

    def save_cache(self):
        """Save current cache to JSON."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"Saved cache with {len(self.cache)} entries")
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    def extract_linkedin_from_website(self, website_url: str) -> str:
        """
        Try to extract LinkedIn URL from company website.
        Looks for LinkedIn link in footer/about pages.

        Returns: LinkedIn profile URL or empty string
        """
        if not website_url or not HAS_REQUESTS:
            return ""

        try:
            # Normalize URL
            if not website_url.startswith(('http://', 'https://')):
                website_url = f'https://{website_url}'

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # Try main page
            response = requests.get(website_url, timeout=5, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for LinkedIn link anywhere on page
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'linkedin.com/company' in href:
                    return href if href.startswith('http') else urljoin(website_url, href)

            # Try /about page
            try:
                about_url = urljoin(website_url, '/about')
                response = requests.get(about_url, timeout=5, headers=headers)
                soup = BeautifulSoup(response.content, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if 'linkedin.com/company' in href:
                        return href if href.startswith('http') else urljoin(website_url, href)
            except:
                pass

        except Exception as e:
            logger.debug(f"Error scraping {website_url}: {e}")

        return ""

    def search_linkedin_playwright(self, company_name: str, city: str = "Dublin") -> str:
        """
        Use Playwright to search Google for company LinkedIn page.
        Slower but more reliable than requests + BeautifulSoup.

        Returns: LinkedIn profile URL or empty string
        """
        if not HAS_PLAYWRIGHT:
            return ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()

                # Search Google for company + LinkedIn
                search_query = f"{company_name} Dublin site:linkedin.com/company"
                page.goto(f"https://www.google.com/search?q={search_query}")
                page.wait_for_timeout(2000)

                # Look for LinkedIn link in results
                links = page.locator('a[href*="linkedin.com/company"]').all()

                for link in links[:1]:  # Take first match
                    href = link.get_attribute('href')
                    if href:
                        browser.close()
                        return href

                browser.close()
        except Exception as e:
            logger.debug(f"Playwright search failed for {company_name}: {e}")

        return ""

    def lookup_linkedin(self, company_name: str, website: str = "", city: str = "Dublin") -> str:
        """
        Lookup LinkedIn URL for a company using multiple methods.

        Strategy:
        1. Check cache
        2. Extract from company website
        3. Search via Playwright (if available)
        4. Return empty if not found

        Args:
            company_name: Business name
            website: Company website URL
            city: City (for search context)

        Returns: LinkedIn profile URL or empty string
        """
        cache_key = company_name.lower().strip()

        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]

        linkedin_url = ""

        # Try extracting from website
        if website:
            linkedin_url = self.extract_linkedin_from_website(website)
            if linkedin_url:
                logger.info(f"Found LinkedIn from website: {company_name}")

        # Try Playwright search if we have it and didn't find anything
        if not linkedin_url and HAS_PLAYWRIGHT:
            linkedin_url = self.search_linkedin_playwright(company_name, city)
            if linkedin_url:
                logger.info(f"Found LinkedIn via search: {company_name}")

        # Cache the result (even if empty)
        self.cache[cache_key] = linkedin_url
        return linkedin_url

    def enrich_csv(self, input_csv: str, output_csv: str, batch_size: int = 5):
        """
        Read input CSV, add LinkedIn URLs, write output CSV.

        Args:
            input_csv: Path to input CSV file
            output_csv: Path to output CSV file
            batch_size: Max concurrent lookups (LinkedIn rate limiting)
        """
        rows = []
        linkedin_urls = {}

        # Read input
        logger.info(f"Reading {input_csv}...")
        with open(input_csv) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        logger.info(f"Found {len(rows)} rows. Starting LinkedIn lookup...")

        # Lookup LinkedIn URLs (single-threaded to be respectful)
        for i, row in enumerate(rows, 1):
            company_name = row.get('business_name', '').strip()
            website = row.get('website', '').strip()
            city = row.get('city', 'Dublin').strip()

            if company_name:
                # Lookup LinkedIn
                linkedin_url = self.lookup_linkedin(company_name, website, city)
                linkedin_urls[company_name] = linkedin_url

                # Rate limiting
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{len(rows)} - Found {sum(1 for u in linkedin_urls.values() if u)} with LinkedIn")
                    time.sleep(2)  # Be respectful to servers

                if i % 50 == 0:
                    self.save_cache()

        # Write output with LinkedIn column
        logger.info(f"Writing output to {output_csv}...")
        fieldnames = rows[0].keys() if rows else []
        fieldnames = list(fieldnames) + ['linkedin_url', 'linkedin_profile_link']

        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for row in rows:
                company_name = row.get('business_name', '').strip()
                linkedin_url = linkedin_urls.get(company_name, '')

                row['linkedin_url'] = linkedin_url
                # Create a markdown-style clickable link for spreadsheets
                if linkedin_url:
                    company_slug = company_name.lower().replace(' ', '-').replace('&', 'and')
                    row['linkedin_profile_link'] = f'=HYPERLINK("{linkedin_url}","{company_name} on LinkedIn")'
                else:
                    row['linkedin_profile_link'] = f'https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(" ", "+")}'

                writer.writerow(row)

        self.save_cache()

        found_count = sum(1 for u in linkedin_urls.values() if u)
        logger.info(f"✅ Complete! Found LinkedIn URLs for {found_count}/{len(rows)} companies")
        logger.info(f"Output saved to: {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description='Enrich Irish print/promo business list with LinkedIn URLs'
    )
    parser.add_argument('--input', default='google-maps-scraper/output/ireland_print_promo.csv',
                        help='Input CSV file')
    parser.add_argument('--output', default='ireland_print_promo_linkedin.csv',
                        help='Output CSV file with LinkedIn URLs')
    parser.add_argument('--cache', default='linkedin_cache.json',
                        help='Cache file for LinkedIn lookups')
    parser.add_argument('--method', choices=['website', 'playwright', 'both'], default='both',
                        help='Lookup method: website scraping, Playwright search, or both')

    args = parser.parse_args()

    # Check requirements
    if args.method in ['both', 'website'] and not HAS_REQUESTS:
        print("⚠️  BeautifulSoup4 not installed. Install with: pip install beautifulsoup4 requests")

    if args.method in ['both', 'playwright'] and not HAS_PLAYWRIGHT:
        print("⚠️  Playwright not installed. Install with: pip install playwright")
        print("   Then run: playwright install chromium")

    if not HAS_REQUESTS and not HAS_PLAYWRIGHT:
        print("❌ No lookup methods available. Install: pip install beautifulsoup4 requests playwright")
        return

    # Run enrichment
    enricher = LinkedInEnricher(cache_file=args.cache)
    enricher.enrich_csv(args.input, args.output)


if __name__ == '__main__':
    main()
