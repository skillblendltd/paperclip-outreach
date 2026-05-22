#!/usr/bin/env python3
"""
Quick LinkedIn CSV Generator for Irish Print & Promo Businesses

Creates a Google Sheet-friendly CSV with:
- Company name, email, phone, website
- LinkedIn search URL (clickable in Excel/Google Sheets)
- Manual entry column for LinkedIn company ID
- Easy copy-paste for bulk LinkedIn connection

Usage:
  python generate_linkedin_csv.py --input google-maps-scraper/output/ireland_print_promo.csv
  python generate_linkedin_csv.py --input ireland_print_promo.csv --output my_list.csv
"""

import csv
import argparse
from pathlib import Path
from urllib.parse import quote

def generate_linkedin_csv(input_csv: str, output_csv: str = None):
    """
    Generate LinkedIn-friendly CSV from prospect list.
    """
    if output_csv is None:
        input_path = Path(input_csv)
        output_csv = input_path.parent / f"{input_path.stem}_linkedin.csv"

    print(f"📖 Reading: {input_csv}")
    rows = []

    with open(input_csv) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"📊 Found {len(rows)} businesses")

    # Generate output
    output_rows = []
    for row in rows:
        company_name = row.get('business_name', '').strip()
        email = row.get('email', '').strip()
        phone = row.get('phone', '').strip()
        website = row.get('website', '').strip()
        city = row.get('city', '').strip()
        region = row.get('region', '').strip()

        if not company_name:
            continue

        # LinkedIn search URL for this company
        search_query = quote(f"{company_name} {city}")
        linkedin_search_url = f"https://www.linkedin.com/search/results/companies/?keywords={search_query}"

        # Google search for LinkedIn
        google_search_url = f"https://www.google.com/search?q={quote(company_name + ' LinkedIn company Ireland')}"

        output_rows.append({
            'company_name': company_name,
            'email': email,
            'phone': phone,
            'website': website,
            'city': city,
            'region': region,
            'linkedin_search': linkedin_search_url,
            'google_search_linkedin': google_search_url,
            'linkedin_company_id': '',  # For manual entry
            'linkedin_company_url': '',  # For result
            'notes': ''
        })

    # Write output
    fieldnames = [
        'company_name', 'email', 'phone', 'website', 'city', 'region',
        'linkedin_search', 'google_search_linkedin', 'linkedin_company_id',
        'linkedin_company_url', 'notes'
    ]

    print(f"✍️  Writing: {output_csv}")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"\n✅ Done!")
    print(f"\n📋 CSV Features:")
    print(f"   - {len(output_rows)} rows ready")
    print(f"   - Column 'linkedin_search': Click to search LinkedIn")
    print(f"   - Column 'google_search_linkedin': Click to search Google")
    print(f"   - Column 'linkedin_company_id': Manual entry (e.g., '12345' from linkedin.com/company/12345)")
    print(f"   - Column 'linkedin_company_url': Auto-fill with formula")
    print(f"\n📖 To use in Google Sheets:")
    print(f"   1. Upload {output_csv} to Google Drive")
    print(f"   2. Open as Google Sheet")
    print(f"   3. Click 'linkedin_search' links to find each company on LinkedIn")
    print(f"   4. Copy the company ID (last number in URL) into 'linkedin_company_id'")
    print(f"   5. Use formula in 'linkedin_company_url': =IF(H2=\"\",\"\",\"https://linkedin.com/company/\"&H2)")
    print(f"\n🤖 Semi-automated approach:")
    print(f"   - Run: pip install beautifulsoup4 requests")
    print(f"   - Run: python linkedin_enrich.py --input {input_csv}")
    print(f"   - Slower but finds LinkedIn URLs automatically")


def main():
    parser = argparse.ArgumentParser(
        description='Generate LinkedIn CSV for Irish print & promo businesses'
    )
    parser.add_argument('--input', default='google-maps-scraper/output/ireland_print_promo.csv',
                        help='Input CSV file (default: ireland_print_promo.csv)')
    parser.add_argument('--output', default=None,
                        help='Output CSV file (default: same dir, _linkedin suffix)')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"❌ Input file not found: {args.input}")
        return

    generate_linkedin_csv(args.input, args.output)


if __name__ == '__main__':
    main()
