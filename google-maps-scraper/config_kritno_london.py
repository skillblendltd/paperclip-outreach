"""
Google Maps Scraper - Kritno Accessibility - LONDON web agencies

Focused entirely on web/digital/UX agencies inside Greater London.
Mirrors the Ireland config's Tier 1 (web agencies) + Tier 5 (marketing/branding overlap).
Tier 2-4 (e-commerce, regulated, hospitality) are EXCLUDED to keep the list tight.

Strategy: borough-level keyword sweeps. Broad-area searches ("Central London, UK")
cap at ~20 top-ranked businesses; borough-level surfaces the local agencies that
don't rank for the broad terms. ~12 keywords x ~12 boroughs = ~144 queries.

Estimated unique web/digital agencies after dedup: 600-1,200.
"""

import os

# -- Rate Limits -----------------------------------------------------------
MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

# -- Output ----------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# -- Keyword set: web/digital/marketing agencies only ----------------------
WEB_AGENCY_KEYWORDS = [
    "web design agency",
    "web development company",
    "digital agency",
    "UX design agency",
    "WordPress agency",
    "Shopify agency",
    "website design company",
    "ecommerce agency",
    "app development company",
    "SEO agency",
    "digital marketing agency",
    "branding agency",
]

# -- Borough sweep ---------------------------------------------------------
# Agency-dense boroughs first (Shoreditch/Clerkenwell/Soho live inside these).
# Skipping pure-residential outer boroughs (Bexley, Sutton, Havering) where
# agency density is near zero.

LONDON_BOROUGHS = [
    "Shoreditch, London, UK",        # agency hub - Tech City
    "Clerkenwell, London, UK",       # agency hub - design district
    "Soho, London, UK",              # agency hub - media/advertising
    "Old Street, London, UK",        # silicon roundabout
    "Hackney, London, UK",
    "Islington, London, UK",
    "Camden, London, UK",
    "Westminster, London, UK",
    "Hammersmith, London, UK",
    "Kensington, London, UK",
    "Chelsea, London, UK",
    "Wandsworth, London, UK",
    "Tower Hamlets, London, UK",
    "Southwark, London, UK",
    "Lambeth, London, UK",
    "Holborn, London, UK",
    "Mayfair, London, UK",
    "Fitzrovia, London, UK",
    "Farringdon, London, UK",
    "Brick Lane, London, UK",
    # Outer M25-ring agency clusters (kept tight - skip for phase 2 if needed)
    "Richmond, London, UK",
    "Kingston upon Thames, London, UK",
    "Croydon, London, UK",
]

SEARCH_QUERIES = [
    {"keyword": kw, "location": loc}
    for loc in LONDON_BOROUGHS
    for kw in WEB_AGENCY_KEYWORDS
]

# -- Segment Mapping -------------------------------------------------------
SEGMENT_MAP = {
    "web design agency":            "web_agency",
    "web development company":      "web_agency",
    "digital agency":               "web_agency",
    "UX design agency":             "web_agency",
    "WordPress agency":             "web_agency",
    "Shopify agency":               "web_agency",
    "website design company":       "web_agency",
    "ecommerce agency":             "web_agency",
    "app development company":      "web_agency",
    "SEO agency":                   "digital_marketing",
    "digital marketing agency":     "digital_marketing",
    "branding agency":              "digital_marketing",
}

# -- Email Filtering -------------------------------------------------------
EMAIL_SKIP_PREFIXES = [
    "noreply", "no-reply", "no_reply",
    "webmaster", "postmaster", "abuse",
    "hostmaster", "mailer-daemon",
]

EMAIL_PREFERRED_PREFIXES = [
    "info", "contact", "hello", "enquiries", "enquiry",
    "sales", "office", "team", "studio", "web",
]

# -- Django Import ---------------------------------------------------------
DJANGO_API_BASE = "http://localhost:8002"
IMPORT_BATCH_SIZE = 200
