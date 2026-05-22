#!/usr/bin/env python3
"""
Generate LinkedIn profile search queries for decision makers at Irish print shops.
Extracts names from emails and creates personalized LinkedIn searches.
"""

import csv
import re
from typing import Tuple

def extract_name_from_email(email: str) -> Tuple[str, str]:
    """
    Extract first and last name from email address.
    Examples:
    - john.hayes@hurricaneprint.ie -> ('John', 'Hayes')
    - info@company.ie -> ('', '')
    """
    if not email or '@' not in email:
        return '', ''

    # Get the local part (before @)
    local_part = email.split('@')[0]

    # Skip generic addresses
    if local_part in ['info', 'sales', 'hello', 'enquiries', 'orders', 'contact', 'office', 'marketing', 'galway', 'paddy', 'gordon', 'charles', 'paul', 'patrick', 'russell', 'john', 'charlemont', 'jferreira', 'jim']:
        return '', ''

    # Split by common separators
    parts = re.split(r'[._-]', local_part)
    parts = [p for p in parts if p and not p.isdigit()]

    if len(parts) >= 2:
        first = parts[0].capitalize()
        last = parts[1].capitalize()
        return first, last
    elif len(parts) == 1:
        return parts[0].capitalize(), ''

    return '', ''


def generate_dm_search_queries(input_file: str, output_file: str):
    """
    Read decision maker data and generate LinkedIn search queries.
    """
    results = []

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            business_name = row.get('business_name', '').strip()
            decision_maker_name = row.get('decision_maker_name', '').strip()
            decision_maker_title = row.get('decision_maker_title', '').strip()
            city = row.get('city', '').strip()
            email = row.get('email', '').strip()

            # Get or extract decision maker name
            if not decision_maker_name:
                # Try to extract from email
                first, last = extract_name_from_email(email)
                if first and last:
                    decision_maker_name = f"{first} {last}"
                elif first:
                    decision_maker_name = first

            if not decision_maker_name:
                # Use generic owner/manager search
                decision_maker_name = f"{business_name} owner"

            # Default title if not provided
            if not decision_maker_title:
                decision_maker_title = "Owner"

            # Build LinkedIn search query
            # For individual profiles
            linkedin_query = f'site:linkedin.com/in/ "{decision_maker_name}"'
            if city:
                linkedin_query += f' {city}'

            # Alternative: search for person + company
            company_query = f'site:linkedin.com "{decision_maker_name}" {business_name}'

            results.append({
                'business_name': business_name,
                'city': city,
                'email': email,
                'decision_maker_name': decision_maker_name,
                'decision_maker_title': decision_maker_title,
                'linkedin_profile_search': linkedin_query,
                'linkedin_company_search': company_query,
                'google_url': f'https://google.com/search?q={linkedin_query.replace(" ", "+")}'
            })

    # Write results to CSV
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        fieldnames = [
            'business_name', 'city', 'email', 'decision_maker_name',
            'decision_maker_title', 'linkedin_profile_search',
            'linkedin_company_search', 'google_url'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    return results


if __name__ == '__main__':
    input_csv = '/tmp/irish_print_shops.csv'
    output_csv = '/tmp/decision_makers_linkedin_search.csv'

    print("Generating LinkedIn profile searches for decision makers...\n")

    results = generate_dm_search_queries(input_csv, output_csv)

    print(f"✓ Generated {len(results)} search queries\n")
    print("Sample searches (first 15):\n")

    for i, r in enumerate(results[:15], 1):
        print(f"{i}. {r['decision_maker_name']} @ {r['business_name']}")
        print(f"   Location: {r['city']}")
        print(f"   Search: {r['linkedin_profile_search']}")
        print()

    print(f"\nFull results saved to: {output_csv}")
    print(f"Total prospects for LinkedIn outreach: {len(results)}")
