"""
Google Maps Scraper — Kritno Accessibility SaaS Prospect Config
Targets: Companies in Ireland that NEED web accessibility compliance.

ICP Segments:
1. Web agencies / digital agencies — they manage client sites, need EAA compliance for ALL of them
2. E-commerce companies — EAA enforcement hitting retailers first
3. SaaS / software companies — their products must be accessible
4. Large businesses with public websites — legal liability under EAA
5. Government / public sector IT — mandatory WCAG compliance
6. Education / universities — accessibility mandates
7. Financial services — heavily regulated, accessibility is part of it
8. Healthcare — patient-facing digital must be accessible

Strategy: Scrape companies that HAVE websites (our scanner needs URLs to demo value).
Then we scan their sites with Kritno, include the score in outreach.
"""

import os

# -- Rate Limits -----------------------------------------------------------
MAPS_SCRAPE_DELAY = 2.0
WEBSITE_SCRAPE_DELAY = 3.0
WEBSITE_TIMEOUT = 15000

# -- Output ----------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# -- Keyword Strategy ------------------------------------------------------
#
# Tier 1 (HIGH PRIORITY) - Direct accessibility buyers:
#   Web agencies, digital agencies, web developers, UX agencies
#   These companies either need compliance themselves OR sell it to clients.
#
# Tier 2 (MEDIUM PRIORITY) - Companies with significant web presence:
#   E-commerce, SaaS, software companies, fintech, online retailers
#   They have customer-facing products that MUST be accessible under EAA.
#
# Tier 3 (COMPLIANCE-DRIVEN) - Regulated / public sector:
#   Government IT, universities, hospitals, financial services
#   Already have accessibility mandates, may need better tooling.
#
# Tier 4 (VOLUME) - Any business with a website they care about:
#   Marketing agencies, corporate companies, hotel chains, retail chains
#   Broad net for the "scan and share" outreach strategy.

SEARCH_QUERIES = [

    # ======================================================================
    # TIER 1: WEB AGENCIES & DIGITAL SERVICES (Primary ICP)
    # Dublin - full coverage (12 keywords)
    # ======================================================================

    # Dublin - Web/Digital agencies
    {"keyword": "web design agency",           "location": "Dublin, Ireland"},
    {"keyword": "web development company",     "location": "Dublin, Ireland"},
    {"keyword": "digital agency",              "location": "Dublin, Ireland"},
    {"keyword": "UX design agency",            "location": "Dublin, Ireland"},
    {"keyword": "WordPress agency",            "location": "Dublin, Ireland"},
    {"keyword": "Shopify agency",              "location": "Dublin, Ireland"},
    {"keyword": "web accessibility consultant","location": "Dublin, Ireland"},
    {"keyword": "website design company",      "location": "Dublin, Ireland"},
    {"keyword": "app development company",     "location": "Dublin, Ireland"},
    {"keyword": "SEO agency",                  "location": "Dublin, Ireland"},
    {"keyword": "digital marketing agency",    "location": "Dublin, Ireland"},
    {"keyword": "ecommerce agency",            "location": "Dublin, Ireland"},

    # Cork - major city
    {"keyword": "web design agency",           "location": "Cork, Ireland"},
    {"keyword": "web development company",     "location": "Cork, Ireland"},
    {"keyword": "digital agency",              "location": "Cork, Ireland"},
    {"keyword": "UX design agency",            "location": "Cork, Ireland"},
    {"keyword": "WordPress agency",            "location": "Cork, Ireland"},
    {"keyword": "Shopify agency",              "location": "Cork, Ireland"},
    {"keyword": "website design company",      "location": "Cork, Ireland"},
    {"keyword": "digital marketing agency",    "location": "Cork, Ireland"},
    {"keyword": "ecommerce agency",            "location": "Cork, Ireland"},
    {"keyword": "app development company",     "location": "Cork, Ireland"},

    # Galway - major city
    {"keyword": "web design agency",           "location": "Galway, Ireland"},
    {"keyword": "web development company",     "location": "Galway, Ireland"},
    {"keyword": "digital agency",              "location": "Galway, Ireland"},
    {"keyword": "WordPress agency",            "location": "Galway, Ireland"},
    {"keyword": "website design company",      "location": "Galway, Ireland"},
    {"keyword": "digital marketing agency",    "location": "Galway, Ireland"},
    {"keyword": "ecommerce agency",            "location": "Galway, Ireland"},
    {"keyword": "SEO agency",                  "location": "Galway, Ireland"},

    # Limerick - mid-size
    {"keyword": "web design agency",           "location": "Limerick, Ireland"},
    {"keyword": "web development company",     "location": "Limerick, Ireland"},
    {"keyword": "digital agency",              "location": "Limerick, Ireland"},
    {"keyword": "WordPress agency",            "location": "Limerick, Ireland"},
    {"keyword": "website design company",      "location": "Limerick, Ireland"},
    {"keyword": "digital marketing agency",    "location": "Limerick, Ireland"},

    # Waterford - mid-size
    {"keyword": "web design agency",           "location": "Waterford, Ireland"},
    {"keyword": "web development company",     "location": "Waterford, Ireland"},
    {"keyword": "digital agency",              "location": "Waterford, Ireland"},
    {"keyword": "website design company",      "location": "Waterford, Ireland"},

    # Kilkenny
    {"keyword": "web design agency",           "location": "Kilkenny, Ireland"},
    {"keyword": "digital agency",              "location": "Kilkenny, Ireland"},
    {"keyword": "website design company",      "location": "Kilkenny, Ireland"},

    # Wexford
    {"keyword": "web design agency",           "location": "Wexford, Ireland"},
    {"keyword": "digital agency",              "location": "Wexford, Ireland"},
    {"keyword": "website design company",      "location": "Wexford, Ireland"},

    # Drogheda / Dundalk
    {"keyword": "web design agency",           "location": "Drogheda, County Louth, Ireland"},
    {"keyword": "web design agency",           "location": "Dundalk, County Louth, Ireland"},
    {"keyword": "digital agency",              "location": "Drogheda, County Louth, Ireland"},

    # Sligo
    {"keyword": "web design agency",           "location": "Sligo, Ireland"},
    {"keyword": "digital agency",              "location": "Sligo, Ireland"},

    # Letterkenny / Donegal
    {"keyword": "web design agency",           "location": "Letterkenny, County Donegal, Ireland"},
    {"keyword": "digital agency",              "location": "Letterkenny, County Donegal, Ireland"},

    # Athlone
    {"keyword": "web design agency",           "location": "Athlone, County Westmeath, Ireland"},
    {"keyword": "digital agency",              "location": "Athlone, County Westmeath, Ireland"},

    # Naas / Kildare
    {"keyword": "web design agency",           "location": "Naas, County Kildare, Ireland"},
    {"keyword": "digital agency",              "location": "Naas, County Kildare, Ireland"},

    # Tralee / Kerry
    {"keyword": "web design agency",           "location": "Tralee, County Kerry, Ireland"},
    {"keyword": "digital agency",              "location": "Tralee, County Kerry, Ireland"},

    # Ennis / Clare
    {"keyword": "web design agency",           "location": "Ennis, County Clare, Ireland"},
    {"keyword": "digital agency",              "location": "Ennis, County Clare, Ireland"},

    # ======================================================================
    # TIER 2: E-COMMERCE & SOFTWARE (High EAA exposure)
    # Focus on Dublin & Cork (where tech companies cluster)
    # ======================================================================

    # Dublin - E-commerce & SaaS
    {"keyword": "ecommerce company",           "location": "Dublin, Ireland"},
    {"keyword": "online retailer",             "location": "Dublin, Ireland"},
    {"keyword": "software company",            "location": "Dublin, Ireland"},
    {"keyword": "SaaS company",                "location": "Dublin, Ireland"},
    {"keyword": "fintech company",             "location": "Dublin, Ireland"},
    {"keyword": "IT company",                  "location": "Dublin, Ireland"},
    {"keyword": "tech startup",                "location": "Dublin, Ireland"},
    {"keyword": "IT services",                 "location": "Dublin, Ireland"},
    {"keyword": "managed IT services",         "location": "Dublin, Ireland"},
    {"keyword": "Shopify store",               "location": "Dublin, Ireland"},

    # Cork - Tech hub
    {"keyword": "software company",            "location": "Cork, Ireland"},
    {"keyword": "IT company",                  "location": "Cork, Ireland"},
    {"keyword": "ecommerce company",           "location": "Cork, Ireland"},
    {"keyword": "tech startup",                "location": "Cork, Ireland"},
    {"keyword": "IT services",                 "location": "Cork, Ireland"},

    # Galway - Tech cluster
    {"keyword": "software company",            "location": "Galway, Ireland"},
    {"keyword": "IT company",                  "location": "Galway, Ireland"},
    {"keyword": "tech startup",                "location": "Galway, Ireland"},
    {"keyword": "IT services",                 "location": "Galway, Ireland"},

    # Limerick - tech growing
    {"keyword": "software company",            "location": "Limerick, Ireland"},
    {"keyword": "IT company",                  "location": "Limerick, Ireland"},
    {"keyword": "IT services",                 "location": "Limerick, Ireland"},

    # ======================================================================
    # TIER 3: COMPLIANCE-DRIVEN SECTORS (Regulated industries)
    # ======================================================================

    # Financial Services (Dublin = EU financial hub)
    {"keyword": "financial services company",  "location": "Dublin, Ireland"},
    {"keyword": "insurance company",           "location": "Dublin, Ireland"},
    {"keyword": "credit union",                "location": "Dublin, Ireland"},
    {"keyword": "bank",                        "location": "Dublin, Ireland"},
    {"keyword": "accounting firm",             "location": "Dublin, Ireland"},
    {"keyword": "credit union",                "location": "Cork, Ireland"},
    {"keyword": "credit union",                "location": "Galway, Ireland"},
    {"keyword": "credit union",                "location": "Limerick, Ireland"},
    {"keyword": "accounting firm",             "location": "Cork, Ireland"},

    # Healthcare (patient portals, public health sites)
    {"keyword": "private hospital",            "location": "Dublin, Ireland"},
    {"keyword": "healthcare company",          "location": "Dublin, Ireland"},
    {"keyword": "medical centre",              "location": "Dublin, Ireland"},
    {"keyword": "health insurance",            "location": "Dublin, Ireland"},

    # Education (university websites, LMS platforms)
    {"keyword": "university",                  "location": "Dublin, Ireland"},
    {"keyword": "college",                     "location": "Dublin, Ireland"},
    {"keyword": "training company",            "location": "Dublin, Ireland"},
    {"keyword": "e-learning company",          "location": "Dublin, Ireland"},
    {"keyword": "university",                  "location": "Cork, Ireland"},
    {"keyword": "university",                  "location": "Galway, Ireland"},
    {"keyword": "college",                     "location": "Limerick, Ireland"},

    # Government / Semi-State
    {"keyword": "government office",           "location": "Dublin, Ireland"},
    {"keyword": "local council",               "location": "Dublin, Ireland"},
    {"keyword": "public service",              "location": "Dublin, Ireland"},

    # ======================================================================
    # TIER 4: VOLUME - Businesses with websites they care about
    # ======================================================================

    # Large Retailers / Hospitality (Dublin)
    {"keyword": "hotel",                       "location": "Dublin, Ireland"},
    {"keyword": "hotel chain",                 "location": "Dublin, Ireland"},
    {"keyword": "retail chain",                "location": "Dublin, Ireland"},
    {"keyword": "shopping centre",             "location": "Dublin, Ireland"},
    {"keyword": "car dealership",              "location": "Dublin, Ireland"},
    {"keyword": "estate agent",                "location": "Dublin, Ireland"},
    {"keyword": "recruitment agency",          "location": "Dublin, Ireland"},
    {"keyword": "travel agency",               "location": "Dublin, Ireland"},
    {"keyword": "law firm",                    "location": "Dublin, Ireland"},

    # Cork volume
    {"keyword": "hotel",                       "location": "Cork, Ireland"},
    {"keyword": "estate agent",                "location": "Cork, Ireland"},
    {"keyword": "recruitment agency",          "location": "Cork, Ireland"},
    {"keyword": "law firm",                    "location": "Cork, Ireland"},
    {"keyword": "car dealership",              "location": "Cork, Ireland"},

    # Galway volume
    {"keyword": "hotel",                       "location": "Galway, Ireland"},
    {"keyword": "estate agent",                "location": "Galway, Ireland"},
    {"keyword": "recruitment agency",          "location": "Galway, Ireland"},
    {"keyword": "law firm",                    "location": "Galway, Ireland"},

    # Limerick volume
    {"keyword": "hotel",                       "location": "Limerick, Ireland"},
    {"keyword": "estate agent",                "location": "Limerick, Ireland"},
    {"keyword": "law firm",                    "location": "Limerick, Ireland"},

    # ======================================================================
    # TIER 5: MARKETING / PR AGENCIES (they influence client decisions)
    # ======================================================================

    {"keyword": "marketing agency",            "location": "Dublin, Ireland"},
    {"keyword": "PR agency",                   "location": "Dublin, Ireland"},
    {"keyword": "branding agency",             "location": "Dublin, Ireland"},
    {"keyword": "content marketing agency",    "location": "Dublin, Ireland"},
    {"keyword": "social media agency",         "location": "Dublin, Ireland"},
    {"keyword": "marketing agency",            "location": "Cork, Ireland"},
    {"keyword": "PR agency",                   "location": "Cork, Ireland"},
    {"keyword": "branding agency",             "location": "Cork, Ireland"},
    {"keyword": "marketing agency",            "location": "Galway, Ireland"},
    {"keyword": "marketing agency",            "location": "Limerick, Ireland"},
]

# -- Segment Mapping -------------------------------------------------------
SEGMENT_MAP = {
    # Tier 1: Web agencies (HIGHEST priority for design partners)
    "web design agency":            "web_agency",
    "web development company":      "web_agency",
    "digital agency":               "web_agency",
    "UX design agency":             "web_agency",
    "WordPress agency":             "web_agency",
    "Shopify agency":               "web_agency",
    "web accessibility consultant": "web_agency",
    "website design company":       "web_agency",
    "app development company":      "web_agency",
    "ecommerce agency":             "web_agency",

    # Tier 1b: SEO/Digital marketing (understand compliance value)
    "SEO agency":                   "digital_marketing",
    "digital marketing agency":     "digital_marketing",
    "marketing agency":             "digital_marketing",
    "PR agency":                    "digital_marketing",
    "branding agency":              "digital_marketing",
    "content marketing agency":     "digital_marketing",
    "social media agency":          "digital_marketing",

    # Tier 2: Tech / SaaS / E-commerce
    "ecommerce company":            "ecommerce",
    "online retailer":              "ecommerce",
    "Shopify store":                "ecommerce",
    "software company":             "tech_company",
    "SaaS company":                 "tech_company",
    "fintech company":              "tech_company",
    "IT company":                   "tech_company",
    "tech startup":                 "tech_company",
    "IT services":                  "tech_company",
    "managed IT services":          "tech_company",

    # Tier 3: Compliance-driven
    "financial services company":   "financial_services",
    "insurance company":            "financial_services",
    "credit union":                 "financial_services",
    "bank":                         "financial_services",
    "accounting firm":              "financial_services",
    "private hospital":             "healthcare",
    "healthcare company":           "healthcare",
    "medical centre":               "healthcare",
    "health insurance":             "healthcare",
    "university":                   "education",
    "college":                      "education",
    "training company":             "education",
    "e-learning company":           "education",
    "government office":            "public_sector",
    "local council":                "public_sector",
    "public service":               "public_sector",

    # Tier 4: Volume
    "hotel":                        "hospitality",
    "hotel chain":                  "hospitality",
    "retail chain":                 "retail",
    "shopping centre":              "retail",
    "car dealership":               "automotive",
    "estate agent":                 "property",
    "recruitment agency":           "recruitment",
    "travel agency":                "travel",
    "law firm":                     "legal",
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
