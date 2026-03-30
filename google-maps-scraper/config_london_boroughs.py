"""
Google Maps Scraper — London Boroughs Configuration
Covers all 33 London boroughs individually for maximum coverage.

Why boroughs vs broad areas:
  Broad area searches ("East London, UK") surface only the top 20-40 businesses.
  Borough-level searches surface local businesses that don't rank for broad terms.

Coverage:
  33 boroughs × 10 keywords = 330 queries
  Estimated unique results: 2,500-4,000 (vs 926 from broad area search)

Output: uk_london_boroughs_20260330.csv (separate from broad-area file)
After both scrapes done: merge + dedup before importing to campaigns.
"""

import os

MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# 10 core keywords — highest signal, widest coverage
KEYWORDS = [
    "promotional products",
    "print shop",
    "embroidery shop",
    "sign shop",
    "custom apparel",
    "screen printing",
    "uniform supplier",
    "signage company",
    "branded merchandise",
    "workwear supplier",
]

# All 33 London boroughs + City of London
BOROUGHS = [
    # Inner London — highest density
    "City of London",
    "Westminster, London",
    "Camden, London",
    "Islington, London",
    "Hackney, London",
    "Tower Hamlets, London",
    "Southwark, London",
    "Lambeth, London",
    "Lewisham, London",
    "Greenwich, London",
    "Wandsworth, London",
    "Hammersmith and Fulham, London",
    "Kensington and Chelsea, London",

    # North London
    "Haringey, London",
    "Enfield, London",
    "Barnet, London",
    "Waltham Forest, London",

    # East London
    "Newham, London",
    "Barking and Dagenham, London",
    "Redbridge, London",
    "Havering, London",
    "Bexley, London",

    # South London
    "Croydon, London",
    "Bromley, London",
    "Merton, London",
    "Sutton, London",
    "Kingston upon Thames, London",

    # West London
    "Ealing, London",
    "Brent, London",
    "Hounslow, London",
    "Hillingdon, London",
    "Richmond upon Thames, London",
    "Harrow, London",
]

SEARCH_QUERIES = [
    {"keyword": keyword, "location": f"{borough}, UK"}
    for borough in BOROUGHS
    for keyword in KEYWORDS
]

# ── Segment Mapping ────────────────────────────────────────
SEGMENT_MAP = {
    "promotional products":   "promo_distributor",
    "branded merchandise":    "promo_distributor",
    "print shop":             "print_shop",
    "screen printing":        "print_shop",
    "embroidery shop":        "apparel_embroidery",
    "custom apparel":         "apparel_embroidery",
    "uniform supplier":       "apparel_embroidery",
    "workwear supplier":      "apparel_embroidery",
    "sign shop":              "signs",
    "signage company":        "signs",
}

EMAIL_SKIP_PREFIXES = [
    "noreply", "no-reply", "no_reply",
    "webmaster", "postmaster", "abuse",
    "hostmaster", "mailer-daemon", "admin",
    "support",
]

EMAIL_PREFERRED_PREFIXES = [
    "info", "contact", "sales", "hello", "enquiries", "enquiry",
    "orders", "studio", "office", "team",
]

DJANGO_API_BASE = "http://localhost:8002"
IMPORT_BATCH_SIZE = 200
