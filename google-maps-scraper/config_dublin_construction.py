"""
Google Maps Scraper - Dublin Construction Companies
Target: ALL construction, building, trades businesses across Dublin for FP branded workwear campaign.
Focus: hi-vis, branded workwear, PPE, uniforms, van signage.
"""

import os

MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Dublin areas - comprehensive coverage
AREAS = [
    "Dublin 1, Ireland",
    "Dublin 2, Ireland",
    "Dublin 4, Ireland",
    "Dublin 6, Ireland",
    "Dublin 8, Ireland",
    "Dublin 9, Ireland",
    "Dublin 11, Ireland",
    "Dublin 12, Ireland",
    "Dublin 15, Ireland",
    "Dublin 22, Ireland",
    "Dublin 24, Ireland",
    "Swords, County Dublin, Ireland",
    "Malahide, County Dublin, Ireland",
    "Howth, County Dublin, Ireland",
    "Dun Laoghaire, County Dublin, Ireland",
    "Bray, County Wicklow, Ireland",
    "Lucan, County Dublin, Ireland",
    "Celbridge, County Kildare, Ireland",
    "Maynooth, County Kildare, Ireland",
    "Naas, County Kildare, Ireland",
]

KEYWORDS = [
    "construction company",
    "building contractor",
    "builder",
    "roofing contractor",
    "plumber",
    "electrician",
    "painter and decorator",
    "plasterer",
    "tiler",
    "landscaping company",
    "fencing contractor",
    "scaffolding company",
    "demolition company",
    "civil engineering",
    "carpentry",
    "flooring company",
    "window installer",
    "insulation company",
    "solar panel installer",
    "property maintenance",
    "renovation company",
    "mechanical contractor",
    "fire protection company",
    "security company",
    "cleaning company",
]

SEARCH_QUERIES = [
    {"keyword": kw, "location": area}
    for area in AREAS
    for kw in KEYWORDS
]

SEGMENT_MAP = {}
MAX_RESULTS_PER_QUERY = 20
