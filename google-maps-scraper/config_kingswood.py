"""
Google Maps Scraper - Kingswood / Dublin 22 Local Businesses
Target: ALL businesses within ~3km of Kingswood Business Park for FP Dublin B2B Corporate Sales.
Focus: companies that need branded merchandise, uniforms, corporate gifts, event materials.
"""

import os

# ── Rate Limits ───────────────────────────────────────────
MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

# ── Output ────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Keywords x Locations ──────────────────────────────────
# Kingswood Business Park is in Dublin 22 (Clondalkin area).
# Nearby areas within 3km: Kingswood, Clondalkin, Belgard, Tallaght,
# Citywest, Saggart, Newcastle, Rathcoole, Park West, Cherry Orchard.
#
# We search for business TYPES that are likely to need branded products:
# - offices, companies, businesses (broad)
# - gym, fitness, sports club (uniforms)
# - restaurant, cafe, hotel (staff uniforms, menus)
# - construction, builder, electrician (workwear)
# - school, creche, childcare (uniforms)
# - car dealership, garage (branded workwear)
# - salon, barber (branded aprons, towels)
# - accountant, solicitor, estate agent (corporate gifts)
# - IT company, tech company (branded merch)
# - recruitment agency (corporate gifts)
# - charity, nonprofit (event merch)

AREAS = [
    "Kingswood, Dublin 22, Ireland",
    "Clondalkin, Dublin 22, Ireland",
    "Belgard, Tallaght, Dublin 24, Ireland",
    "Citywest, Dublin 24, Ireland",
    "Park West, Dublin 12, Ireland",
    "Ballymount, Dublin 12, Ireland",
]

KEYWORDS = [
    "businesses",
    "office",
    "company",
    "gym",
    "fitness centre",
    "restaurant",
    "cafe",
    "hotel",
    "construction company",
    "school",
    "creche",
    "car dealership",
    "garage",
    "salon",
    "barber",
    "accountant",
    "solicitor",
    "estate agent",
    "IT company",
    "recruitment agency",
    "sports club",
    "pharmacy",
    "dental clinic",
    "veterinary clinic",
]

SEARCH_QUERIES = [
    {"keyword": kw, "location": area}
    for area in AREAS
    for kw in KEYWORDS
]

# ── Segment mapping ──────────────────────────────────────
# For FP B2B, all businesses are potential customers.
# We'll classify later based on business_category from Google Maps.
SEGMENT_MAP = {}

# ── Max results per query ────────────────────────────────
MAX_RESULTS_PER_QUERY = 20
