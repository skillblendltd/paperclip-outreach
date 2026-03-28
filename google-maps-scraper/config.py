"""
Google Maps Scraper — Configuration
Targets: promotional products, embroidery, custom apparel, sign shops, print shops
All 26 counties, Republic of Ireland.
"""

import os

# ── Rate Limits ───────────────────────────────────────────
MAPS_SCRAPE_DELAY = 2.0      # seconds between scroll rounds
WEBSITE_SCRAPE_DELAY = 3.0    # seconds between website visits
WEBSITE_TIMEOUT = 15000       # ms, Playwright page load timeout

# ── Output ────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Keyword Groups ────────────────────────────────────────
# Major cities: all 8 keywords
# Mid-size towns: 5 core keywords
# Small county towns: 3 keywords
#
# Core (everywhere):       promotional products, embroidery shop, print shop, sign shop
# Extended (mid+major):    custom apparel, screen printing, uniform supplier, signage company
# Major only:              branded merchandise, corporate gifts, workwear, banner printing

SEARCH_QUERIES = [

    # ════════════════════════════════════════════════════════
    # LEINSTER
    # ════════════════════════════════════════════════════════

    # Dublin — major city, full coverage
    {"keyword": "promotional products",  "location": "Dublin, Ireland"},
    {"keyword": "embroidery shop",        "location": "Dublin, Ireland"},
    {"keyword": "print shop",             "location": "Dublin, Ireland"},
    {"keyword": "sign shop",              "location": "Dublin, Ireland"},
    {"keyword": "custom apparel",         "location": "Dublin, Ireland"},
    {"keyword": "screen printing",        "location": "Dublin, Ireland"},
    {"keyword": "uniform supplier",       "location": "Dublin, Ireland"},
    {"keyword": "signage company",        "location": "Dublin, Ireland"},
    {"keyword": "branded merchandise",    "location": "Dublin, Ireland"},
    {"keyword": "corporate gifts",        "location": "Dublin, Ireland"},
    {"keyword": "workwear supplier",      "location": "Dublin, Ireland"},
    {"keyword": "banner printing",        "location": "Dublin, Ireland"},

    # Kildare — mid-size (Naas / Newbridge)
    {"keyword": "promotional products",  "location": "Naas, County Kildare, Ireland"},
    {"keyword": "embroidery shop",        "location": "Naas, County Kildare, Ireland"},
    {"keyword": "print shop",             "location": "Naas, County Kildare, Ireland"},
    {"keyword": "sign shop",              "location": "Naas, County Kildare, Ireland"},
    {"keyword": "custom apparel",         "location": "Newbridge, County Kildare, Ireland"},

    # Meath — mid-size (Navan)
    {"keyword": "promotional products",  "location": "Navan, County Meath, Ireland"},
    {"keyword": "embroidery shop",        "location": "Navan, County Meath, Ireland"},
    {"keyword": "print shop",             "location": "Navan, County Meath, Ireland"},
    {"keyword": "sign shop",              "location": "Navan, County Meath, Ireland"},
    {"keyword": "uniform supplier",       "location": "Navan, County Meath, Ireland"},

    # Louth — mid-size (Drogheda / Dundalk)
    {"keyword": "promotional products",  "location": "Drogheda, County Louth, Ireland"},
    {"keyword": "promotional products",  "location": "Dundalk, County Louth, Ireland"},
    {"keyword": "embroidery shop",        "location": "Dundalk, County Louth, Ireland"},
    {"keyword": "print shop",             "location": "Drogheda, County Louth, Ireland"},
    {"keyword": "sign shop",              "location": "Dundalk, County Louth, Ireland"},
    {"keyword": "custom apparel",         "location": "Drogheda, County Louth, Ireland"},

    # Wicklow — mid-size (Bray / Wicklow)
    {"keyword": "promotional products",  "location": "Bray, County Wicklow, Ireland"},
    {"keyword": "embroidery shop",        "location": "Bray, County Wicklow, Ireland"},
    {"keyword": "print shop",             "location": "Wicklow, Ireland"},
    {"keyword": "sign shop",              "location": "Bray, County Wicklow, Ireland"},
    {"keyword": "custom apparel",         "location": "Bray, County Wicklow, Ireland"},

    # Wexford — mid-size
    {"keyword": "promotional products",  "location": "Wexford, Ireland"},
    {"keyword": "embroidery shop",        "location": "Wexford, Ireland"},
    {"keyword": "print shop",             "location": "Wexford, Ireland"},
    {"keyword": "sign shop",              "location": "Wexford, Ireland"},
    {"keyword": "custom apparel",         "location": "Wexford, Ireland"},

    # Kilkenny — mid-size
    {"keyword": "promotional products",  "location": "Kilkenny, Ireland"},
    {"keyword": "embroidery shop",        "location": "Kilkenny, Ireland"},
    {"keyword": "print shop",             "location": "Kilkenny, Ireland"},
    {"keyword": "sign shop",              "location": "Kilkenny, Ireland"},
    {"keyword": "custom apparel",         "location": "Kilkenny, Ireland"},

    # Westmeath — mid-size (Athlone)
    {"keyword": "promotional products",  "location": "Athlone, County Westmeath, Ireland"},
    {"keyword": "embroidery shop",        "location": "Athlone, County Westmeath, Ireland"},
    {"keyword": "print shop",             "location": "Athlone, County Westmeath, Ireland"},
    {"keyword": "sign shop",              "location": "Athlone, County Westmeath, Ireland"},
    {"keyword": "custom apparel",         "location": "Athlone, County Westmeath, Ireland"},

    # Carlow — small
    {"keyword": "promotional products",  "location": "Carlow, Ireland"},
    {"keyword": "embroidery shop",        "location": "Carlow, Ireland"},
    {"keyword": "print shop",             "location": "Carlow, Ireland"},
    {"keyword": "sign shop",              "location": "Carlow, Ireland"},

    # Laois — small (Portlaoise)
    {"keyword": "promotional products",  "location": "Portlaoise, County Laois, Ireland"},
    {"keyword": "embroidery shop",        "location": "Portlaoise, County Laois, Ireland"},
    {"keyword": "print shop",             "location": "Portlaoise, County Laois, Ireland"},
    {"keyword": "sign shop",              "location": "Portlaoise, County Laois, Ireland"},

    # Offaly — small (Tullamore)
    {"keyword": "promotional products",  "location": "Tullamore, County Offaly, Ireland"},
    {"keyword": "embroidery shop",        "location": "Tullamore, County Offaly, Ireland"},
    {"keyword": "print shop",             "location": "Tullamore, County Offaly, Ireland"},
    {"keyword": "sign shop",              "location": "Tullamore, County Offaly, Ireland"},

    # Longford — small
    {"keyword": "promotional products",  "location": "Longford, Ireland"},
    {"keyword": "embroidery shop",        "location": "Longford, Ireland"},
    {"keyword": "print shop",             "location": "Longford, Ireland"},
    {"keyword": "sign shop",              "location": "Longford, Ireland"},

    # ════════════════════════════════════════════════════════
    # MUNSTER
    # ════════════════════════════════════════════════════════

    # Cork — major city, full coverage
    {"keyword": "promotional products",  "location": "Cork, Ireland"},
    {"keyword": "embroidery shop",        "location": "Cork, Ireland"},
    {"keyword": "print shop",             "location": "Cork, Ireland"},
    {"keyword": "sign shop",              "location": "Cork, Ireland"},
    {"keyword": "custom apparel",         "location": "Cork, Ireland"},
    {"keyword": "screen printing",        "location": "Cork, Ireland"},
    {"keyword": "uniform supplier",       "location": "Cork, Ireland"},
    {"keyword": "signage company",        "location": "Cork, Ireland"},
    {"keyword": "branded merchandise",    "location": "Cork, Ireland"},
    {"keyword": "workwear supplier",      "location": "Cork, Ireland"},
    {"keyword": "banner printing",        "location": "Cork, Ireland"},

    # Limerick — mid-size
    {"keyword": "promotional products",  "location": "Limerick, Ireland"},
    {"keyword": "embroidery shop",        "location": "Limerick, Ireland"},
    {"keyword": "print shop",             "location": "Limerick, Ireland"},
    {"keyword": "sign shop",              "location": "Limerick, Ireland"},
    {"keyword": "custom apparel",         "location": "Limerick, Ireland"},
    {"keyword": "uniform supplier",       "location": "Limerick, Ireland"},

    # Waterford — mid-size
    {"keyword": "promotional products",  "location": "Waterford, Ireland"},
    {"keyword": "embroidery shop",        "location": "Waterford, Ireland"},
    {"keyword": "print shop",             "location": "Waterford, Ireland"},
    {"keyword": "sign shop",              "location": "Waterford, Ireland"},
    {"keyword": "custom apparel",         "location": "Waterford, Ireland"},

    # Kerry — mid-size (Tralee / Killarney)
    {"keyword": "promotional products",  "location": "Tralee, County Kerry, Ireland"},
    {"keyword": "promotional products",  "location": "Killarney, County Kerry, Ireland"},
    {"keyword": "embroidery shop",        "location": "Tralee, County Kerry, Ireland"},
    {"keyword": "print shop",             "location": "Tralee, County Kerry, Ireland"},
    {"keyword": "sign shop",              "location": "Tralee, County Kerry, Ireland"},
    {"keyword": "custom apparel",         "location": "Tralee, County Kerry, Ireland"},

    # Clare — mid-size (Ennis)
    {"keyword": "promotional products",  "location": "Ennis, County Clare, Ireland"},
    {"keyword": "embroidery shop",        "location": "Ennis, County Clare, Ireland"},
    {"keyword": "print shop",             "location": "Ennis, County Clare, Ireland"},
    {"keyword": "sign shop",              "location": "Ennis, County Clare, Ireland"},
    {"keyword": "custom apparel",         "location": "Ennis, County Clare, Ireland"},

    # Tipperary — mid-size (Clonmel / Thurles)
    {"keyword": "promotional products",  "location": "Clonmel, County Tipperary, Ireland"},
    {"keyword": "promotional products",  "location": "Thurles, County Tipperary, Ireland"},
    {"keyword": "embroidery shop",        "location": "Clonmel, County Tipperary, Ireland"},
    {"keyword": "print shop",             "location": "Clonmel, County Tipperary, Ireland"},
    {"keyword": "sign shop",              "location": "Clonmel, County Tipperary, Ireland"},
    {"keyword": "custom apparel",         "location": "Clonmel, County Tipperary, Ireland"},

    # ════════════════════════════════════════════════════════
    # CONNACHT
    # ════════════════════════════════════════════════════════

    # Galway — major city, full coverage
    {"keyword": "promotional products",  "location": "Galway, Ireland"},
    {"keyword": "embroidery shop",        "location": "Galway, Ireland"},
    {"keyword": "print shop",             "location": "Galway, Ireland"},
    {"keyword": "sign shop",              "location": "Galway, Ireland"},
    {"keyword": "custom apparel",         "location": "Galway, Ireland"},
    {"keyword": "screen printing",        "location": "Galway, Ireland"},
    {"keyword": "uniform supplier",       "location": "Galway, Ireland"},
    {"keyword": "branded merchandise",    "location": "Galway, Ireland"},
    {"keyword": "workwear supplier",      "location": "Galway, Ireland"},

    # Mayo — mid-size (Castlebar / Ballina)
    {"keyword": "promotional products",  "location": "Castlebar, County Mayo, Ireland"},
    {"keyword": "promotional products",  "location": "Ballina, County Mayo, Ireland"},
    {"keyword": "embroidery shop",        "location": "Castlebar, County Mayo, Ireland"},
    {"keyword": "print shop",             "location": "Castlebar, County Mayo, Ireland"},
    {"keyword": "sign shop",              "location": "Castlebar, County Mayo, Ireland"},
    {"keyword": "custom apparel",         "location": "Castlebar, County Mayo, Ireland"},

    # Sligo — mid-size
    {"keyword": "promotional products",  "location": "Sligo, Ireland"},
    {"keyword": "embroidery shop",        "location": "Sligo, Ireland"},
    {"keyword": "print shop",             "location": "Sligo, Ireland"},
    {"keyword": "sign shop",              "location": "Sligo, Ireland"},
    {"keyword": "custom apparel",         "location": "Sligo, Ireland"},

    # Roscommon — small
    {"keyword": "promotional products",  "location": "Roscommon, Ireland"},
    {"keyword": "embroidery shop",        "location": "Roscommon, Ireland"},
    {"keyword": "print shop",             "location": "Roscommon, Ireland"},
    {"keyword": "sign shop",              "location": "Roscommon, Ireland"},

    # Leitrim — small (Carrick-on-Shannon)
    {"keyword": "promotional products",  "location": "Carrick-on-Shannon, County Leitrim, Ireland"},
    {"keyword": "embroidery shop",        "location": "Carrick-on-Shannon, County Leitrim, Ireland"},
    {"keyword": "print shop",             "location": "Carrick-on-Shannon, County Leitrim, Ireland"},
    {"keyword": "sign shop",              "location": "Carrick-on-Shannon, County Leitrim, Ireland"},

    # ════════════════════════════════════════════════════════
    # ULSTER (Republic of Ireland)
    # ════════════════════════════════════════════════════════

    # Donegal — mid-size (Letterkenny / Donegal Town)
    {"keyword": "promotional products",  "location": "Letterkenny, County Donegal, Ireland"},
    {"keyword": "promotional products",  "location": "Donegal Town, Ireland"},
    {"keyword": "embroidery shop",        "location": "Letterkenny, County Donegal, Ireland"},
    {"keyword": "print shop",             "location": "Letterkenny, County Donegal, Ireland"},
    {"keyword": "sign shop",              "location": "Letterkenny, County Donegal, Ireland"},
    {"keyword": "custom apparel",         "location": "Letterkenny, County Donegal, Ireland"},

    # Cavan — small
    {"keyword": "promotional products",  "location": "Cavan, Ireland"},
    {"keyword": "embroidery shop",        "location": "Cavan, Ireland"},
    {"keyword": "print shop",             "location": "Cavan, Ireland"},
    {"keyword": "sign shop",              "location": "Cavan, Ireland"},

    # Monaghan — small
    {"keyword": "promotional products",  "location": "Monaghan, Ireland"},
    {"keyword": "embroidery shop",        "location": "Monaghan, Ireland"},
    {"keyword": "print shop",             "location": "Monaghan, Ireland"},
    {"keyword": "sign shop",              "location": "Monaghan, Ireland"},
]

# ── Segment Mapping ───────────────────────────────────────
# Maps search keyword to Prospect segment value
SEGMENT_MAP = {
    # Promo
    "promotional products": "promo_distributor",
    "promo distributor":    "promo_distributor",
    "branded merchandise":  "promo_distributor",
    "corporate gifts":      "promo_distributor",
    # Apparel / embroidery
    "embroidery shop":      "apparel_embroidery",
    "embroidery":           "apparel_embroidery",
    "custom embroidery":    "apparel_embroidery",
    "custom apparel":       "apparel_embroidery",
    "uniform supplier":     "apparel_embroidery",
    "uniform":              "apparel_embroidery",
    "workwear supplier":    "apparel_embroidery",
    "workwear":             "apparel_embroidery",
    # Print
    "print shop":           "print_shop",
    "custom print shop":    "print_shop",
    "screen printing":      "print_shop",
    "banner printing":      "print_shop",
    "print agency":         "print_shop",
    # Signs
    "sign shop":            "signs",
    "signs":                "signs",
    "signage":              "signs",
    "signage company":      "signs",
    # Other
    "trophy":               "mixed",
    "trophy engraving":     "mixed",
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
