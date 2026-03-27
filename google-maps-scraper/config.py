"""
Google Maps Scraper — Configuration
Free Playwright-based scraper. No API key needed.
Searches for print, promo, and embroidery shops.
"""

import os

# ── Rate Limits ───────────────────────────────────────────
MAPS_SCRAPE_DELAY = 2.0      # seconds between scroll rounds
WEBSITE_SCRAPE_DELAY = 3.0    # seconds between website visits
WEBSITE_TIMEOUT = 15000       # ms, Playwright page load timeout

# ── Output ────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Search Queries ────────────────────────────────────────
# Each dict: keyword + location. Add as many as needed.
# The scraper runs all of these unless --query/--location is passed.
SEARCH_QUERIES = [
    # Ireland — primary market
    {"keyword": "promotional products", "location": "Dublin, Ireland"},
    {"keyword": "promotional products", "location": "Cork, Ireland"},
    {"keyword": "promotional products", "location": "Galway, Ireland"},
    {"keyword": "promotional products", "location": "Limerick, Ireland"},
    {"keyword": "promotional products", "location": "Waterford, Ireland"},
    {"keyword": "embroidery shop", "location": "Dublin, Ireland"},
    {"keyword": "embroidery shop", "location": "Cork, Ireland"},
    {"keyword": "embroidery shop", "location": "Galway, Ireland"},
    {"keyword": "custom print shop", "location": "Dublin, Ireland"},
    {"keyword": "custom print shop", "location": "Cork, Ireland"},
    {"keyword": "screen printing", "location": "Dublin, Ireland"},
    {"keyword": "screen printing", "location": "Cork, Ireland"},
    {"keyword": "branded merchandise", "location": "Dublin, Ireland"},
    {"keyword": "corporate gifts", "location": "Dublin, Ireland"},
    {"keyword": "uniform supplier", "location": "Dublin, Ireland"},
    {"keyword": "uniform supplier", "location": "Cork, Ireland"},
    {"keyword": "signage company", "location": "Dublin, Ireland"},
    {"keyword": "trophy engraving", "location": "Dublin, Ireland"},
]

# ── Segment Mapping ───────────────────────────────────────
# Maps search keyword to Prospect segment value
SEGMENT_MAP = {
    "promotional products": "promo_distributor",
    "promo distributor": "promo_distributor",
    "branded merchandise": "promo_distributor",
    "corporate gifts": "promo_distributor",
    "embroidery": "apparel_embroidery",
    "embroidery shop": "apparel_embroidery",
    "custom embroidery": "apparel_embroidery",
    "uniform": "apparel_embroidery",
    "uniform supplier": "apparel_embroidery",
    "print shop": "print_shop",
    "custom print shop": "print_shop",
    "screen printing": "print_shop",
    "signs": "signs",
    "signage": "signs",
    "signage company": "signs",
    "trophy": "mixed",
    "trophy engraving": "mixed",
    "print agency": "print_agency",
}

# ── Email Filtering ───────────────────────────────────────
# Skip emails starting with these prefixes
EMAIL_SKIP_PREFIXES = [
    "noreply", "no-reply", "no_reply",
    "webmaster", "postmaster", "abuse",
    "hostmaster", "mailer-daemon", "admin",
    "support",
]

# Prefer these email prefixes (ranked)
EMAIL_PREFERRED_PREFIXES = [
    "info", "contact", "sales", "hello", "enquiries", "enquiry",
    "orders", "studio", "office", "team",
]

# ── Django Import ─────────────────────────────────────────
DJANGO_API_BASE = "http://localhost:8002"
IMPORT_BATCH_SIZE = 200
