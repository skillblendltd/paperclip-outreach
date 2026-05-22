#!/usr/bin/env python3
"""
Generate LinkedIn search queries for Irish print shops.
Uses manual Google/WebSearch lookups.
"""

import csv
import sys

def generate_search_queries(input_file: str):
    """Generate search queries for each print shop."""
    queries = []

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            business_name = row.get('business_name', '').strip()
            city = row.get('city', '').strip()

            if business_name:
                # LinkedIn company search
                query = f'site:linkedin.com "{business_name}"'
                if city:
                    query += f' {city}'

                queries.append({
                    'company': business_name,
                    'city': city,
                    'email': row.get('email', ''),
                    'query': query,
                    'google_url': f'https://google.com/search?q={query.replace(" ", "+")}'
                })

    return queries


if __name__ == '__main__':
    input_csv = '/tmp/irish_print_shops.csv'

    print(f"Generating LinkedIn search queries...\n")

    queries = generate_search_queries(input_csv)

    print(f"Generated {len(queries)} search queries\n")
    print("Top 20 searches to manually check:\n")

    for i, q in enumerate(queries[:20], 1):
        print(f"{i}. {q['company']} ({q['city']})")
        print(f"   Email: {q['email']}")
        print(f"   Google: {q['google_url']}")
        print()

    # Save all queries to file
    with open('/tmp/linkedin_search_queries.txt', 'w') as f:
        for q in queries:
            f.write(f"{q['company']} | {q['city']} | {q['email']} | {q['google_url']}\n")

    print(f"\nSaved all {len(queries)} queries to /tmp/linkedin_search_queries.txt")
