"""
Google Maps Scraper — London Configuration
Targets: print, promo, embroidery, decoration, signs businesses across all London areas.

Areas:
  Central London — DONE in uk_print_promo_20260329.csv
  North London   — DONE in uk_print_promo_20260329.csv
  South London   — PARTIAL in uk_print_promo_20260329.csv
  East London    — TODO
  West London    — TODO

Keywords: core print/promo + decoration-specific (DTF, screen printing, heat transfer, sublimation)

Output: uk_london_20260329.csv (resume from existing file)
"""

import os

MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

SEARCH_QUERIES = [

    # ── CENTRAL LONDON (already done — will be skipped on resume) ──────────
    {"keyword": "promotional products",  "location": "Central London, UK"},
    {"keyword": "embroidery shop",        "location": "Central London, UK"},
    {"keyword": "print shop",             "location": "Central London, UK"},
    {"keyword": "sign shop",              "location": "Central London, UK"},
    {"keyword": "custom apparel",         "location": "Central London, UK"},
    {"keyword": "screen printing",        "location": "Central London, UK"},
    {"keyword": "uniform supplier",       "location": "Central London, UK"},
    {"keyword": "signage company",        "location": "Central London, UK"},
    {"keyword": "branded merchandise",    "location": "Central London, UK"},
    {"keyword": "corporate gifts",        "location": "Central London, UK"},
    {"keyword": "workwear supplier",      "location": "Central London, UK"},
    {"keyword": "banner printing",        "location": "Central London, UK"},
    {"keyword": "DTF printing",           "location": "Central London, UK"},
    {"keyword": "garment decoration",     "location": "Central London, UK"},
    {"keyword": "heat transfer printing", "location": "Central London, UK"},
    {"keyword": "sublimation printing",   "location": "Central London, UK"},

    # ── NORTH LONDON (already done — will be skipped on resume) ───────────
    {"keyword": "promotional products",  "location": "North London, UK"},
    {"keyword": "embroidery shop",        "location": "North London, UK"},
    {"keyword": "print shop",             "location": "North London, UK"},
    {"keyword": "sign shop",              "location": "North London, UK"},
    {"keyword": "custom apparel",         "location": "North London, UK"},
    {"keyword": "screen printing",        "location": "North London, UK"},
    {"keyword": "uniform supplier",       "location": "North London, UK"},
    {"keyword": "signage company",        "location": "North London, UK"},
    {"keyword": "branded merchandise",    "location": "North London, UK"},
    {"keyword": "workwear supplier",      "location": "North London, UK"},
    {"keyword": "DTF printing",           "location": "North London, UK"},
    {"keyword": "garment decoration",     "location": "North London, UK"},
    {"keyword": "heat transfer printing", "location": "North London, UK"},
    {"keyword": "sublimation printing",   "location": "North London, UK"},

    # ── SOUTH LONDON (partially done — new keywords will run) ─────────────
    {"keyword": "promotional products",  "location": "South London, UK"},
    {"keyword": "embroidery shop",        "location": "South London, UK"},
    {"keyword": "print shop",             "location": "South London, UK"},
    {"keyword": "sign shop",              "location": "South London, UK"},
    {"keyword": "custom apparel",         "location": "South London, UK"},
    {"keyword": "screen printing",        "location": "South London, UK"},
    {"keyword": "uniform supplier",       "location": "South London, UK"},
    {"keyword": "signage company",        "location": "South London, UK"},
    {"keyword": "branded merchandise",    "location": "South London, UK"},
    {"keyword": "workwear supplier",      "location": "South London, UK"},
    {"keyword": "DTF printing",           "location": "South London, UK"},
    {"keyword": "garment decoration",     "location": "South London, UK"},
    {"keyword": "heat transfer printing", "location": "South London, UK"},
    {"keyword": "sublimation printing",   "location": "South London, UK"},
    {"keyword": "banner printing",        "location": "South London, UK"},
    {"keyword": "corporate gifts",        "location": "South London, UK"},

    # ── EAST LONDON ────────────────────────────────────────────────────────
    {"keyword": "promotional products",  "location": "East London, UK"},
    {"keyword": "embroidery shop",        "location": "East London, UK"},
    {"keyword": "print shop",             "location": "East London, UK"},
    {"keyword": "sign shop",              "location": "East London, UK"},
    {"keyword": "custom apparel",         "location": "East London, UK"},
    {"keyword": "screen printing",        "location": "East London, UK"},
    {"keyword": "uniform supplier",       "location": "East London, UK"},
    {"keyword": "signage company",        "location": "East London, UK"},
    {"keyword": "branded merchandise",    "location": "East London, UK"},
    {"keyword": "workwear supplier",      "location": "East London, UK"},
    {"keyword": "DTF printing",           "location": "East London, UK"},
    {"keyword": "garment decoration",     "location": "East London, UK"},
    {"keyword": "heat transfer printing", "location": "East London, UK"},
    {"keyword": "sublimation printing",   "location": "East London, UK"},
    {"keyword": "banner printing",        "location": "East London, UK"},
    {"keyword": "corporate gifts",        "location": "East London, UK"},

    # ── WEST LONDON ────────────────────────────────────────────────────────
    {"keyword": "promotional products",  "location": "West London, UK"},
    {"keyword": "embroidery shop",        "location": "West London, UK"},
    {"keyword": "print shop",             "location": "West London, UK"},
    {"keyword": "sign shop",              "location": "West London, UK"},
    {"keyword": "custom apparel",         "location": "West London, UK"},
    {"keyword": "screen printing",        "location": "West London, UK"},
    {"keyword": "uniform supplier",       "location": "West London, UK"},
    {"keyword": "signage company",        "location": "West London, UK"},
    {"keyword": "branded merchandise",    "location": "West London, UK"},
    {"keyword": "workwear supplier",      "location": "West London, UK"},
    {"keyword": "DTF printing",           "location": "West London, UK"},
    {"keyword": "garment decoration",     "location": "West London, UK"},
    {"keyword": "heat transfer printing", "location": "West London, UK"},
    {"keyword": "sublimation printing",   "location": "West London, UK"},
    {"keyword": "banner printing",        "location": "West London, UK"},
    {"keyword": "corporate gifts",        "location": "West London, UK"},
]

# ── Segment Mapping ───────────────────────────────────────
SEGMENT_MAP = {
    "promotional products":  "promo_distributor",
    "branded merchandise":   "promo_distributor",
    "corporate gifts":       "promo_distributor",
    "embroidery shop":       "apparel_embroidery",
    "custom apparel":        "apparel_embroidery",
    "uniform supplier":      "apparel_embroidery",
    "workwear supplier":     "apparel_embroidery",
    "garment decoration":    "apparel_embroidery",
    "print shop":            "print_shop",
    "screen printing":       "print_shop",
    "banner printing":       "print_shop",
    "DTF printing":          "print_shop",
    "heat transfer printing":"print_shop",
    "sublimation printing":  "print_shop",
    "sign shop":             "signs",
    "signage company":       "signs",
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
