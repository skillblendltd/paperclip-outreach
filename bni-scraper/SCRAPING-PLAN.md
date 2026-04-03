# BNI Global Scraping — Structure & Plan

## Goal
Scrape all BNI members by country, organized so we can:
- Filter by country for targeted campaigns
- Filter by specialty (print, promo, embroidery, signage, apparel)
- Avoid duplicates across scrape runs
- Track what's been scraped vs. what's pending

---

## Directory Structure

```
bni-scraper/
├── scrape_bni.py                    # Main scraper (updated)
├── configs/                         # Country-specific scrape configs
│   ├── uk.json
│   ├── ireland.json
│   ├── usa.json
│   ├── canada.json
│   ├── australia.json
│   ├── south_africa.json
│   └── ...
├── output/
│   ├── raw/                         # Raw scrape output, one file per country per run
│   │   ├── uk_20260402.csv
│   │   ├── ireland_20260402.csv
│   │   ├── usa_20260403.csv
│   │   └── ...
│   ├── merged/                      # Deduplicated master files per country
│   │   ├── uk_all.csv
│   │   ├── ireland_all.csv
│   │   ├── usa_all.csv
│   │   └── ...
│   ├── bni_master.csv               # Global master — all countries merged + deduped
│   └── bni_chapter_gaps.xlsx        # Analysis output
├── merge_countries.py               # Merge raw → country master → global master
├── filter_specialties.py            # Filter master by specialty keywords
└── SCRAPING-PLAN.md                 # This file
```

---

## Config File Format (`configs/<country>.json`)

Each country config tells the scraper what to search for and how:

```json
{
  "country_code": "uk",
  "country_name": "United Kingdom",
  "bni_search_country": "United Kingdom",
  "searches": [
    {
      "keyword": "",
      "description": "All members (blank keyword = everyone)"
    }
  ],
  "status": "pending",
  "last_scraped": null,
  "total_members": null,
  "notes": ""
}
```

### Search strategy per country

BNI Connect search allows filtering by:
- **Country** (dropdown)
- **Keyword** (free text — matches name, specialty, company)

For small countries (<500 members), a single blank-keyword search gets everyone.
For large countries (USA, UK), you may need multiple keyword searches to get past scroll limits, then deduplicate.

---

## Priority Countries

### Tier 1 — Active campaigns / immediate pipeline
| Country | Est. Members | Product | Config | Status |
|---------|-------------|---------|--------|--------|
| Ireland | ~400 | FP + TaggIQ | `ireland.json` | **Done** (fpdublin_bni_mail_list.csv) |
| United Kingdom | ~5,000+ | TaggIQ | `uk.json` | Pending |

### Tier 2 — TaggIQ global (English-speaking, strong BNI presence)
| Country | Est. Members | Config | Status |
|---------|-------------|--------|--------|
| United States | ~30,000+ | `usa.json` | Partial (promo only) |
| Canada | ~3,000+ | `canada.json` | Pending |
| Australia | ~3,000+ | `australia.json` | Pending |
| South Africa | ~1,500+ | `south_africa.json` | Pending |
| India | ~2,000+ | `india.json` | Pending |

### Tier 3 — TaggIQ expansion (English proficiency + promo industry)
| Country | Config | Status |
|---------|--------|--------|
| Germany | `germany.json` | Pending |
| France | `france.json` | Pending |
| Spain | `spain.json` | Pending |
| Italy | `italy.json` | Pending |
| Malaysia | `malaysia.json` | Pending |
| Brazil | `brazil.json` | Pending |
| Mexico | `mexico.json` | Pending |
| South Korea | `south_korea.json` | Pending |

---

## CSV Schema (all output files)

Same fields as current scraper — consistent across all countries:

| Field | Source | Description |
|-------|--------|-------------|
| `name` | List view | Full name |
| `email` | Detail page | Email address |
| `phone` | Detail page | Phone number(s) |
| `company` | **List view** | Company name (NOT on detail page) |
| `chapter` | Both | BNI chapter name |
| `city` | Both | City |
| `postcode` | Detail page | Postal code |
| `country` | Detail page / config | Country |
| `specialty` | Both | Profession & Specialty from list |
| `website` | Detail page | Business website |
| `address` | Detail page | Full address |
| `professional_details` | Detail page | Full bio/description text |
| `profile_url` | List view | BNI Connect profile URL |

---

## Scrape Workflow

### Step 1: Pick a country config
```bash
# List available configs and their status
python3 scrape_bni.py --list-configs

# Or just pick one
python3 scrape_bni.py --config configs/uk.json
```

### Step 2: Run the scraper
```bash
# Full scrape — all members in country
python3 scrape_bni.py --config configs/uk.json -o output/raw/uk_20260402.csv

# Test with 5 contacts first
python3 scrape_bni.py --config configs/uk.json --max 5 -o output/raw/uk_test.csv
```

### Step 3: Merge & deduplicate
```bash
# Merge all raw files for a country into one master
python3 merge_countries.py --country uk

# Rebuild global master from all country masters
python3 merge_countries.py --all
```

### Step 4: Filter by specialty
```bash
# Get all print/promo/sign/embroidery people in UK
python3 filter_specialties.py --country uk --type print_promo

# Get all members in UK (for FP-style chapter gap analysis)
python3 filter_specialties.py --country uk --type all
```

---

## Deduplication Rules

Deduplicate by `profile_url` (contains unique `userId`). This is the only reliable unique key since:
- Same person can appear in multiple keyword searches
- Names aren't unique
- Email can be missing
- Same email can belong to different businesses

### Merge priority (when same userId appears in multiple raw files):
1. Keep the record with the most non-empty fields
2. For fields present in both, prefer the newer scrape

---

## Filtering Specialties

Standard keyword groups for filtering:

| Filter Name | Keywords (checked in specialty + professional_details) |
|------------|------------------------------------------------------|
| `print` | printer, printing products, printing & signage, print company, print service, digital print, large format, commercial print |
| `promo` | promotional products, promotional merchandise, branded merchandise, corporate gift, branded gift |
| `apparel` | embroidery, uniform, workwear, corporate wear, branded clothing, garment print, t-shirt print, screen print, sublimation, clothing & accessories, custom clothing, sportswear |
| `signage` | sign company, signage, sign manufacturer, sign maker, vehicle wrap, vehicle graphic, window graphic, vinyl wrap |
| `print_promo` | All of the above combined |
| `all` | No filter — all members |

---

## Large Country Strategy (USA, UK)

BNI Connect has scroll limits (~500-1000 results per search). For countries with thousands of members:

### Option A: Search by region/state
Break into multiple searches by filtering region in the BNI search UI:
- UK: England, Scotland, Wales, Northern Ireland → then by county
- USA: by state (50 searches)
- The scraper pauses for manual search setup anyway, so this works

### Option B: Search by specialty keyword
Run separate searches for each specialty keyword:
- "printer", "promotional", "embroidery", "sign", "apparel", etc.
- Then merge and deduplicate
- Misses members outside our target specialties (fine for TaggIQ campaigns)

### Option C: Search alphabetically
Search by first letter of name (A, B, C...) if no other filter works.

**Recommended: Option A for full scrape, Option B for targeted campaigns.**

---

## Tracking Scrape Progress

Update each config's `status` and `last_scraped` after each run:

| Status | Meaning |
|--------|---------|
| `pending` | Not started |
| `in_progress` | Partially scraped (large countries) |
| `done` | Fully scraped, merged |
| `stale` | Scraped but >90 days old, needs refresh |

---

## What We Already Have

| File | Country | Members | Emails | Specialty Filter |
|------|---------|---------|--------|-----------------|
| `fpdublin_bni_mail_list.csv` | Ireland | 425 | ~200 | All (Dublin BNI chapters) |
| `bni_promo_global.csv` | Global | 1,718 | ~800 | Promotional Products |
| `bni_embroidery_global.csv` | Global | 347 | ~150 | Embroidery |
| `bni_contacts.csv` | Ireland | 347 | ~150 | Print & Promo (Ireland) |

These should be reorganized into the new structure:
- `fpdublin_bni_mail_list.csv` → `output/merged/ireland_all.csv`
- `bni_promo_global.csv` → keep as-is (multi-country, specialty-filtered)
- `bni_embroidery_global.csv` → keep as-is (multi-country, specialty-filtered)
