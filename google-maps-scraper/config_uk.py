"""
Google Maps Scraper — UK Configuration
Targets: promotional products, embroidery, custom apparel, sign shops, print shops
Coverage: England, Scotland, Wales, Northern Ireland

Tier 1 — Major cities (12 keywords):  London (5 areas), Manchester, Birmingham, Glasgow
Tier 2 — Large cities (8-9 keywords): Edinburgh, Leeds, Liverpool, Bristol, Newcastle, Sheffield
Tier 3 — Medium cities (6 keywords):  Nottingham, Leicester, Cardiff, Aberdeen, Sheffield...
Tier 4 — Smaller towns (4 keywords):  Regional centres across all nations

Estimated queries: ~450 | Estimated businesses: 5,000-10,000
"""

import os

# ── Rate Limits ───────────────────────────────────────────
MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

# ── Output ────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Search Queries ────────────────────────────────────────

SEARCH_QUERIES = [

    # ════════════════════════════════════════════════════════
    # LONDON — split by area (Tier 1, 12 keywords each area)
    # ════════════════════════════════════════════════════════
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

    {"keyword": "promotional products",  "location": "North London, UK"},
    {"keyword": "embroidery shop",        "location": "North London, UK"},
    {"keyword": "print shop",             "location": "North London, UK"},
    {"keyword": "sign shop",              "location": "North London, UK"},
    {"keyword": "custom apparel",         "location": "North London, UK"},
    {"keyword": "screen printing",        "location": "North London, UK"},
    {"keyword": "uniform supplier",       "location": "North London, UK"},
    {"keyword": "signage company",        "location": "North London, UK"},
    {"keyword": "branded merchandise",    "location": "North London, UK"},
    {"keyword": "corporate gifts",        "location": "North London, UK"},
    {"keyword": "workwear supplier",      "location": "North London, UK"},

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

    # ════════════════════════════════════════════════════════
    # MANCHESTER — Tier 1 (12 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Manchester, UK"},
    {"keyword": "embroidery shop",        "location": "Manchester, UK"},
    {"keyword": "print shop",             "location": "Manchester, UK"},
    {"keyword": "sign shop",              "location": "Manchester, UK"},
    {"keyword": "custom apparel",         "location": "Manchester, UK"},
    {"keyword": "screen printing",        "location": "Manchester, UK"},
    {"keyword": "uniform supplier",       "location": "Manchester, UK"},
    {"keyword": "signage company",        "location": "Manchester, UK"},
    {"keyword": "branded merchandise",    "location": "Manchester, UK"},
    {"keyword": "corporate gifts",        "location": "Manchester, UK"},
    {"keyword": "workwear supplier",      "location": "Manchester, UK"},
    {"keyword": "banner printing",        "location": "Manchester, UK"},

    # ════════════════════════════════════════════════════════
    # BIRMINGHAM — Tier 1 (12 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Birmingham, UK"},
    {"keyword": "embroidery shop",        "location": "Birmingham, UK"},
    {"keyword": "print shop",             "location": "Birmingham, UK"},
    {"keyword": "sign shop",             "location": "Birmingham, UK"},
    {"keyword": "custom apparel",         "location": "Birmingham, UK"},
    {"keyword": "screen printing",        "location": "Birmingham, UK"},
    {"keyword": "uniform supplier",       "location": "Birmingham, UK"},
    {"keyword": "signage company",        "location": "Birmingham, UK"},
    {"keyword": "branded merchandise",    "location": "Birmingham, UK"},
    {"keyword": "corporate gifts",        "location": "Birmingham, UK"},
    {"keyword": "workwear supplier",      "location": "Birmingham, UK"},
    {"keyword": "banner printing",        "location": "Birmingham, UK"},

    # ════════════════════════════════════════════════════════
    # GLASGOW — Tier 1 (12 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Glasgow, UK"},
    {"keyword": "embroidery shop",        "location": "Glasgow, UK"},
    {"keyword": "print shop",             "location": "Glasgow, UK"},
    {"keyword": "sign shop",              "location": "Glasgow, UK"},
    {"keyword": "custom apparel",         "location": "Glasgow, UK"},
    {"keyword": "screen printing",        "location": "Glasgow, UK"},
    {"keyword": "uniform supplier",       "location": "Glasgow, UK"},
    {"keyword": "signage company",        "location": "Glasgow, UK"},
    {"keyword": "branded merchandise",    "location": "Glasgow, UK"},
    {"keyword": "corporate gifts",        "location": "Glasgow, UK"},
    {"keyword": "workwear supplier",      "location": "Glasgow, UK"},
    {"keyword": "banner printing",        "location": "Glasgow, UK"},

    # ════════════════════════════════════════════════════════
    # EDINBURGH — Tier 2 (9 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Edinburgh, UK"},
    {"keyword": "embroidery shop",        "location": "Edinburgh, UK"},
    {"keyword": "print shop",             "location": "Edinburgh, UK"},
    {"keyword": "sign shop",              "location": "Edinburgh, UK"},
    {"keyword": "custom apparel",         "location": "Edinburgh, UK"},
    {"keyword": "screen printing",        "location": "Edinburgh, UK"},
    {"keyword": "uniform supplier",       "location": "Edinburgh, UK"},
    {"keyword": "signage company",        "location": "Edinburgh, UK"},
    {"keyword": "branded merchandise",    "location": "Edinburgh, UK"},

    # ════════════════════════════════════════════════════════
    # LEEDS — Tier 2 (9 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Leeds, UK"},
    {"keyword": "embroidery shop",        "location": "Leeds, UK"},
    {"keyword": "print shop",             "location": "Leeds, UK"},
    {"keyword": "sign shop",              "location": "Leeds, UK"},
    {"keyword": "custom apparel",         "location": "Leeds, UK"},
    {"keyword": "screen printing",        "location": "Leeds, UK"},
    {"keyword": "uniform supplier",       "location": "Leeds, UK"},
    {"keyword": "signage company",        "location": "Leeds, UK"},
    {"keyword": "workwear supplier",      "location": "Leeds, UK"},

    # ════════════════════════════════════════════════════════
    # LIVERPOOL — Tier 2 (9 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Liverpool, UK"},
    {"keyword": "embroidery shop",        "location": "Liverpool, UK"},
    {"keyword": "print shop",             "location": "Liverpool, UK"},
    {"keyword": "sign shop",              "location": "Liverpool, UK"},
    {"keyword": "custom apparel",         "location": "Liverpool, UK"},
    {"keyword": "screen printing",        "location": "Liverpool, UK"},
    {"keyword": "uniform supplier",       "location": "Liverpool, UK"},
    {"keyword": "signage company",        "location": "Liverpool, UK"},
    {"keyword": "workwear supplier",      "location": "Liverpool, UK"},

    # ════════════════════════════════════════════════════════
    # BRISTOL — Tier 2 (9 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Bristol, UK"},
    {"keyword": "embroidery shop",        "location": "Bristol, UK"},
    {"keyword": "print shop",             "location": "Bristol, UK"},
    {"keyword": "sign shop",              "location": "Bristol, UK"},
    {"keyword": "custom apparel",         "location": "Bristol, UK"},
    {"keyword": "screen printing",        "location": "Bristol, UK"},
    {"keyword": "uniform supplier",       "location": "Bristol, UK"},
    {"keyword": "signage company",        "location": "Bristol, UK"},
    {"keyword": "workwear supplier",      "location": "Bristol, UK"},

    # ════════════════════════════════════════════════════════
    # NEWCASTLE UPON TYNE — Tier 2 (8 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Newcastle upon Tyne, UK"},
    {"keyword": "embroidery shop",        "location": "Newcastle upon Tyne, UK"},
    {"keyword": "print shop",             "location": "Newcastle upon Tyne, UK"},
    {"keyword": "sign shop",              "location": "Newcastle upon Tyne, UK"},
    {"keyword": "custom apparel",         "location": "Newcastle upon Tyne, UK"},
    {"keyword": "screen printing",        "location": "Newcastle upon Tyne, UK"},
    {"keyword": "uniform supplier",       "location": "Newcastle upon Tyne, UK"},
    {"keyword": "signage company",        "location": "Newcastle upon Tyne, UK"},

    # ════════════════════════════════════════════════════════
    # SHEFFIELD — Tier 2 (8 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Sheffield, UK"},
    {"keyword": "embroidery shop",        "location": "Sheffield, UK"},
    {"keyword": "print shop",             "location": "Sheffield, UK"},
    {"keyword": "sign shop",              "location": "Sheffield, UK"},
    {"keyword": "custom apparel",         "location": "Sheffield, UK"},
    {"keyword": "screen printing",        "location": "Sheffield, UK"},
    {"keyword": "uniform supplier",       "location": "Sheffield, UK"},
    {"keyword": "workwear supplier",      "location": "Sheffield, UK"},

    # ════════════════════════════════════════════════════════
    # NOTTINGHAM — Tier 3 (6 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Nottingham, UK"},
    {"keyword": "embroidery shop",        "location": "Nottingham, UK"},
    {"keyword": "print shop",             "location": "Nottingham, UK"},
    {"keyword": "sign shop",              "location": "Nottingham, UK"},
    {"keyword": "custom apparel",         "location": "Nottingham, UK"},
    {"keyword": "uniform supplier",       "location": "Nottingham, UK"},

    # ════════════════════════════════════════════════════════
    # LEICESTER — Tier 3 (6 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Leicester, UK"},
    {"keyword": "embroidery shop",        "location": "Leicester, UK"},
    {"keyword": "print shop",             "location": "Leicester, UK"},
    {"keyword": "sign shop",              "location": "Leicester, UK"},
    {"keyword": "custom apparel",         "location": "Leicester, UK"},
    {"keyword": "uniform supplier",       "location": "Leicester, UK"},

    # ════════════════════════════════════════════════════════
    # CARDIFF — Wales Tier 2 (9 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Cardiff, Wales, UK"},
    {"keyword": "embroidery shop",        "location": "Cardiff, Wales, UK"},
    {"keyword": "print shop",             "location": "Cardiff, Wales, UK"},
    {"keyword": "sign shop",              "location": "Cardiff, Wales, UK"},
    {"keyword": "custom apparel",         "location": "Cardiff, Wales, UK"},
    {"keyword": "screen printing",        "location": "Cardiff, Wales, UK"},
    {"keyword": "uniform supplier",       "location": "Cardiff, Wales, UK"},
    {"keyword": "signage company",        "location": "Cardiff, Wales, UK"},
    {"keyword": "workwear supplier",      "location": "Cardiff, Wales, UK"},

    # ════════════════════════════════════════════════════════
    # ABERDEEN — Scotland Tier 3 (6 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Aberdeen, Scotland, UK"},
    {"keyword": "embroidery shop",        "location": "Aberdeen, Scotland, UK"},
    {"keyword": "print shop",             "location": "Aberdeen, Scotland, UK"},
    {"keyword": "sign shop",              "location": "Aberdeen, Scotland, UK"},
    {"keyword": "custom apparel",         "location": "Aberdeen, Scotland, UK"},
    {"keyword": "uniform supplier",       "location": "Aberdeen, Scotland, UK"},

    # ════════════════════════════════════════════════════════
    # BELFAST — Northern Ireland Tier 2 (9 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "embroidery shop",        "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "print shop",             "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "sign shop",              "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "custom apparel",         "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "screen printing",        "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "uniform supplier",       "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "signage company",        "location": "Belfast, Northern Ireland, UK"},
    {"keyword": "workwear supplier",      "location": "Belfast, Northern Ireland, UK"},

    # ════════════════════════════════════════════════════════
    # ENGLAND — Tier 3 Medium Cities (6 keywords each)
    # ════════════════════════════════════════════════════════

    # Coventry
    {"keyword": "promotional products",  "location": "Coventry, UK"},
    {"keyword": "embroidery shop",        "location": "Coventry, UK"},
    {"keyword": "print shop",             "location": "Coventry, UK"},
    {"keyword": "sign shop",              "location": "Coventry, UK"},
    {"keyword": "custom apparel",         "location": "Coventry, UK"},
    {"keyword": "uniform supplier",       "location": "Coventry, UK"},

    # Southampton
    {"keyword": "promotional products",  "location": "Southampton, UK"},
    {"keyword": "embroidery shop",        "location": "Southampton, UK"},
    {"keyword": "print shop",             "location": "Southampton, UK"},
    {"keyword": "sign shop",              "location": "Southampton, UK"},
    {"keyword": "custom apparel",         "location": "Southampton, UK"},
    {"keyword": "uniform supplier",       "location": "Southampton, UK"},

    # Portsmouth
    {"keyword": "promotional products",  "location": "Portsmouth, UK"},
    {"keyword": "embroidery shop",        "location": "Portsmouth, UK"},
    {"keyword": "print shop",             "location": "Portsmouth, UK"},
    {"keyword": "sign shop",              "location": "Portsmouth, UK"},
    {"keyword": "custom apparel",         "location": "Portsmouth, UK"},
    {"keyword": "uniform supplier",       "location": "Portsmouth, UK"},

    # Plymouth
    {"keyword": "promotional products",  "location": "Plymouth, UK"},
    {"keyword": "embroidery shop",        "location": "Plymouth, UK"},
    {"keyword": "print shop",             "location": "Plymouth, UK"},
    {"keyword": "sign shop",              "location": "Plymouth, UK"},
    {"keyword": "custom apparel",         "location": "Plymouth, UK"},
    {"keyword": "uniform supplier",       "location": "Plymouth, UK"},

    # Bradford
    {"keyword": "promotional products",  "location": "Bradford, UK"},
    {"keyword": "embroidery shop",        "location": "Bradford, UK"},
    {"keyword": "print shop",             "location": "Bradford, UK"},
    {"keyword": "sign shop",              "location": "Bradford, UK"},
    {"keyword": "custom apparel",         "location": "Bradford, UK"},
    {"keyword": "uniform supplier",       "location": "Bradford, UK"},

    # Wolverhampton
    {"keyword": "promotional products",  "location": "Wolverhampton, UK"},
    {"keyword": "embroidery shop",        "location": "Wolverhampton, UK"},
    {"keyword": "print shop",             "location": "Wolverhampton, UK"},
    {"keyword": "sign shop",              "location": "Wolverhampton, UK"},
    {"keyword": "custom apparel",         "location": "Wolverhampton, UK"},
    {"keyword": "uniform supplier",       "location": "Wolverhampton, UK"},

    # Derby
    {"keyword": "promotional products",  "location": "Derby, UK"},
    {"keyword": "embroidery shop",        "location": "Derby, UK"},
    {"keyword": "print shop",             "location": "Derby, UK"},
    {"keyword": "sign shop",              "location": "Derby, UK"},
    {"keyword": "custom apparel",         "location": "Derby, UK"},
    {"keyword": "uniform supplier",       "location": "Derby, UK"},

    # Stoke-on-Trent
    {"keyword": "promotional products",  "location": "Stoke-on-Trent, UK"},
    {"keyword": "embroidery shop",        "location": "Stoke-on-Trent, UK"},
    {"keyword": "print shop",             "location": "Stoke-on-Trent, UK"},
    {"keyword": "sign shop",              "location": "Stoke-on-Trent, UK"},
    {"keyword": "custom apparel",         "location": "Stoke-on-Trent, UK"},
    {"keyword": "uniform supplier",       "location": "Stoke-on-Trent, UK"},

    # Sunderland
    {"keyword": "promotional products",  "location": "Sunderland, UK"},
    {"keyword": "embroidery shop",        "location": "Sunderland, UK"},
    {"keyword": "print shop",             "location": "Sunderland, UK"},
    {"keyword": "sign shop",              "location": "Sunderland, UK"},
    {"keyword": "custom apparel",         "location": "Sunderland, UK"},
    {"keyword": "uniform supplier",       "location": "Sunderland, UK"},

    # Reading
    {"keyword": "promotional products",  "location": "Reading, UK"},
    {"keyword": "embroidery shop",        "location": "Reading, UK"},
    {"keyword": "print shop",             "location": "Reading, UK"},
    {"keyword": "sign shop",              "location": "Reading, UK"},
    {"keyword": "custom apparel",         "location": "Reading, UK"},
    {"keyword": "uniform supplier",       "location": "Reading, UK"},

    # Milton Keynes
    {"keyword": "promotional products",  "location": "Milton Keynes, UK"},
    {"keyword": "embroidery shop",        "location": "Milton Keynes, UK"},
    {"keyword": "print shop",             "location": "Milton Keynes, UK"},
    {"keyword": "sign shop",              "location": "Milton Keynes, UK"},
    {"keyword": "custom apparel",         "location": "Milton Keynes, UK"},
    {"keyword": "uniform supplier",       "location": "Milton Keynes, UK"},

    # Northampton
    {"keyword": "promotional products",  "location": "Northampton, UK"},
    {"keyword": "embroidery shop",        "location": "Northampton, UK"},
    {"keyword": "print shop",             "location": "Northampton, UK"},
    {"keyword": "sign shop",              "location": "Northampton, UK"},
    {"keyword": "custom apparel",         "location": "Northampton, UK"},
    {"keyword": "uniform supplier",       "location": "Northampton, UK"},

    # Luton
    {"keyword": "promotional products",  "location": "Luton, UK"},
    {"keyword": "embroidery shop",        "location": "Luton, UK"},
    {"keyword": "print shop",             "location": "Luton, UK"},
    {"keyword": "sign shop",              "location": "Luton, UK"},
    {"keyword": "custom apparel",         "location": "Luton, UK"},
    {"keyword": "uniform supplier",       "location": "Luton, UK"},

    # Exeter
    {"keyword": "promotional products",  "location": "Exeter, UK"},
    {"keyword": "embroidery shop",        "location": "Exeter, UK"},
    {"keyword": "print shop",             "location": "Exeter, UK"},
    {"keyword": "sign shop",              "location": "Exeter, UK"},
    {"keyword": "custom apparel",         "location": "Exeter, UK"},
    {"keyword": "uniform supplier",       "location": "Exeter, UK"},

    # Brighton
    {"keyword": "promotional products",  "location": "Brighton, UK"},
    {"keyword": "embroidery shop",        "location": "Brighton, UK"},
    {"keyword": "print shop",             "location": "Brighton, UK"},
    {"keyword": "sign shop",              "location": "Brighton, UK"},
    {"keyword": "custom apparel",         "location": "Brighton, UK"},
    {"keyword": "uniform supplier",       "location": "Brighton, UK"},

    # ════════════════════════════════════════════════════════
    # ENGLAND — Tier 4 Smaller towns (4 keywords each)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "York, UK"},
    {"keyword": "embroidery shop",        "location": "York, UK"},
    {"keyword": "print shop",             "location": "York, UK"},
    {"keyword": "sign shop",              "location": "York, UK"},

    {"keyword": "promotional products",  "location": "Oxford, UK"},
    {"keyword": "embroidery shop",        "location": "Oxford, UK"},
    {"keyword": "print shop",             "location": "Oxford, UK"},
    {"keyword": "sign shop",              "location": "Oxford, UK"},

    {"keyword": "promotional products",  "location": "Cambridge, UK"},
    {"keyword": "embroidery shop",        "location": "Cambridge, UK"},
    {"keyword": "print shop",             "location": "Cambridge, UK"},
    {"keyword": "sign shop",              "location": "Cambridge, UK"},

    {"keyword": "promotional products",  "location": "Norwich, UK"},
    {"keyword": "embroidery shop",        "location": "Norwich, UK"},
    {"keyword": "print shop",             "location": "Norwich, UK"},
    {"keyword": "sign shop",              "location": "Norwich, UK"},

    {"keyword": "promotional products",  "location": "Ipswich, UK"},
    {"keyword": "embroidery shop",        "location": "Ipswich, UK"},
    {"keyword": "print shop",             "location": "Ipswich, UK"},
    {"keyword": "sign shop",              "location": "Ipswich, UK"},

    {"keyword": "promotional products",  "location": "Peterborough, UK"},
    {"keyword": "embroidery shop",        "location": "Peterborough, UK"},
    {"keyword": "print shop",             "location": "Peterborough, UK"},
    {"keyword": "sign shop",              "location": "Peterborough, UK"},

    {"keyword": "promotional products",  "location": "Cheltenham, UK"},
    {"keyword": "embroidery shop",        "location": "Cheltenham, UK"},
    {"keyword": "print shop",             "location": "Cheltenham, UK"},
    {"keyword": "sign shop",              "location": "Cheltenham, UK"},

    {"keyword": "promotional products",  "location": "Gloucester, UK"},
    {"keyword": "embroidery shop",        "location": "Gloucester, UK"},
    {"keyword": "print shop",             "location": "Gloucester, UK"},
    {"keyword": "sign shop",              "location": "Gloucester, UK"},

    {"keyword": "promotional products",  "location": "Worcester, UK"},
    {"keyword": "embroidery shop",        "location": "Worcester, UK"},
    {"keyword": "print shop",             "location": "Worcester, UK"},
    {"keyword": "sign shop",              "location": "Worcester, UK"},

    {"keyword": "promotional products",  "location": "Swindon, UK"},
    {"keyword": "embroidery shop",        "location": "Swindon, UK"},
    {"keyword": "print shop",             "location": "Swindon, UK"},
    {"keyword": "sign shop",              "location": "Swindon, UK"},

    {"keyword": "promotional products",  "location": "Huddersfield, UK"},
    {"keyword": "embroidery shop",        "location": "Huddersfield, UK"},
    {"keyword": "print shop",             "location": "Huddersfield, UK"},
    {"keyword": "sign shop",              "location": "Huddersfield, UK"},

    {"keyword": "promotional products",  "location": "Hull, UK"},
    {"keyword": "embroidery shop",        "location": "Hull, UK"},
    {"keyword": "print shop",             "location": "Hull, UK"},
    {"keyword": "sign shop",              "location": "Hull, UK"},

    {"keyword": "promotional products",  "location": "Middlesbrough, UK"},
    {"keyword": "embroidery shop",        "location": "Middlesbrough, UK"},
    {"keyword": "print shop",             "location": "Middlesbrough, UK"},
    {"keyword": "sign shop",              "location": "Middlesbrough, UK"},

    {"keyword": "promotional products",  "location": "Blackpool, UK"},
    {"keyword": "embroidery shop",        "location": "Blackpool, UK"},
    {"keyword": "print shop",             "location": "Blackpool, UK"},
    {"keyword": "sign shop",              "location": "Blackpool, UK"},

    {"keyword": "promotional products",  "location": "Preston, Lancashire, UK"},
    {"keyword": "embroidery shop",        "location": "Preston, Lancashire, UK"},
    {"keyword": "print shop",             "location": "Preston, Lancashire, UK"},
    {"keyword": "sign shop",              "location": "Preston, Lancashire, UK"},

    {"keyword": "promotional products",  "location": "Bolton, UK"},
    {"keyword": "embroidery shop",        "location": "Bolton, UK"},
    {"keyword": "print shop",             "location": "Bolton, UK"},
    {"keyword": "sign shop",              "location": "Bolton, UK"},

    {"keyword": "promotional products",  "location": "Stockport, UK"},
    {"keyword": "embroidery shop",        "location": "Stockport, UK"},
    {"keyword": "print shop",             "location": "Stockport, UK"},
    {"keyword": "sign shop",              "location": "Stockport, UK"},

    {"keyword": "promotional products",  "location": "Wigan, UK"},
    {"keyword": "embroidery shop",        "location": "Wigan, UK"},
    {"keyword": "print shop",             "location": "Wigan, UK"},
    {"keyword": "sign shop",              "location": "Wigan, UK"},

    {"keyword": "promotional products",  "location": "Warrington, UK"},
    {"keyword": "embroidery shop",        "location": "Warrington, UK"},
    {"keyword": "print shop",             "location": "Warrington, UK"},
    {"keyword": "sign shop",              "location": "Warrington, UK"},

    {"keyword": "promotional products",  "location": "Chester, UK"},
    {"keyword": "embroidery shop",        "location": "Chester, UK"},
    {"keyword": "print shop",             "location": "Chester, UK"},
    {"keyword": "sign shop",              "location": "Chester, UK"},

    {"keyword": "promotional products",  "location": "Shrewsbury, UK"},
    {"keyword": "embroidery shop",        "location": "Shrewsbury, UK"},
    {"keyword": "print shop",             "location": "Shrewsbury, UK"},
    {"keyword": "sign shop",              "location": "Shrewsbury, UK"},

    {"keyword": "promotional products",  "location": "Hereford, UK"},
    {"keyword": "embroidery shop",        "location": "Hereford, UK"},
    {"keyword": "print shop",             "location": "Hereford, UK"},
    {"keyword": "sign shop",              "location": "Hereford, UK"},

    # ════════════════════════════════════════════════════════
    # SCOTLAND — Tier 3/4 (4-6 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Dundee, Scotland, UK"},
    {"keyword": "embroidery shop",        "location": "Dundee, Scotland, UK"},
    {"keyword": "print shop",             "location": "Dundee, Scotland, UK"},
    {"keyword": "sign shop",              "location": "Dundee, Scotland, UK"},
    {"keyword": "custom apparel",         "location": "Dundee, Scotland, UK"},
    {"keyword": "uniform supplier",       "location": "Dundee, Scotland, UK"},

    {"keyword": "promotional products",  "location": "Inverness, Scotland, UK"},
    {"keyword": "embroidery shop",        "location": "Inverness, Scotland, UK"},
    {"keyword": "print shop",             "location": "Inverness, Scotland, UK"},
    {"keyword": "sign shop",              "location": "Inverness, Scotland, UK"},

    {"keyword": "promotional products",  "location": "Stirling, Scotland, UK"},
    {"keyword": "embroidery shop",        "location": "Stirling, Scotland, UK"},
    {"keyword": "print shop",             "location": "Stirling, Scotland, UK"},
    {"keyword": "sign shop",              "location": "Stirling, Scotland, UK"},

    {"keyword": "promotional products",  "location": "Perth, Scotland, UK"},
    {"keyword": "embroidery shop",        "location": "Perth, Scotland, UK"},
    {"keyword": "print shop",             "location": "Perth, Scotland, UK"},
    {"keyword": "sign shop",              "location": "Perth, Scotland, UK"},

    # ════════════════════════════════════════════════════════
    # WALES — Medium / Small (4-6 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Swansea, Wales, UK"},
    {"keyword": "embroidery shop",        "location": "Swansea, Wales, UK"},
    {"keyword": "print shop",             "location": "Swansea, Wales, UK"},
    {"keyword": "sign shop",              "location": "Swansea, Wales, UK"},
    {"keyword": "custom apparel",         "location": "Swansea, Wales, UK"},
    {"keyword": "uniform supplier",       "location": "Swansea, Wales, UK"},

    {"keyword": "promotional products",  "location": "Newport, Wales, UK"},
    {"keyword": "embroidery shop",        "location": "Newport, Wales, UK"},
    {"keyword": "print shop",             "location": "Newport, Wales, UK"},
    {"keyword": "sign shop",              "location": "Newport, Wales, UK"},

    {"keyword": "promotional products",  "location": "Wrexham, Wales, UK"},
    {"keyword": "embroidery shop",        "location": "Wrexham, Wales, UK"},
    {"keyword": "print shop",             "location": "Wrexham, Wales, UK"},
    {"keyword": "sign shop",              "location": "Wrexham, Wales, UK"},

    # ════════════════════════════════════════════════════════
    # NORTHERN IRELAND — Additional cities (4 keywords)
    # ════════════════════════════════════════════════════════
    {"keyword": "promotional products",  "location": "Derry, Northern Ireland, UK"},
    {"keyword": "embroidery shop",        "location": "Derry, Northern Ireland, UK"},
    {"keyword": "print shop",             "location": "Derry, Northern Ireland, UK"},
    {"keyword": "sign shop",              "location": "Derry, Northern Ireland, UK"},
]

# ── Segment Mapping — same as Ireland config ──────────────
SEGMENT_MAP = {
    "promotional products": "promo_distributor",
    "promo distributor":    "promo_distributor",
    "branded merchandise":  "promo_distributor",
    "corporate gifts":      "promo_distributor",
    "embroidery shop":      "apparel_embroidery",
    "embroidery":           "apparel_embroidery",
    "custom embroidery":    "apparel_embroidery",
    "custom apparel":       "apparel_embroidery",
    "uniform supplier":     "apparel_embroidery",
    "uniform":              "apparel_embroidery",
    "workwear supplier":    "apparel_embroidery",
    "workwear":             "apparel_embroidery",
    "print shop":           "print_shop",
    "custom print shop":    "print_shop",
    "screen printing":      "print_shop",
    "banner printing":      "print_shop",
    "print agency":         "print_shop",
    "sign shop":            "signs",
    "signs":                "signs",
    "signage":              "signs",
    "signage company":      "signs",
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
