#!/usr/bin/env python3
"""
Batch LinkedIn finder - processes decision makers and collects found URLs.
Use with WebSearch tool to find LinkedIn profiles, then import URLs back to database.
"""

import csv
import json
from datetime import datetime

def create_batch_search_file(input_csv: str, output_json: str, batch_size: int = 50):
    """
    Create a batch search file with LinkedIn profile search instructions.
    Each entry can be manually searched or batch-processed with WebSearch.
    """
    searches = []

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            dm_name = row.get('decision_maker_name', '').strip()
            business = row.get('business_name', '').strip()
            city = row.get('city', '').strip()
            email = row.get('email', '').strip()

            if not dm_name or 'owner' in dm_name.lower():
                continue

            # Create search query
            search_query = f'site:linkedin.com/in/ "{dm_name}" {city}'

            searches.append({
                'search_id': len(searches) + 1,
                'name': dm_name,
                'company': business,
                'city': city,
                'email': email,
                'search_query': search_query,
                'found_url': None,
                'status': 'pending'
            })

    # Save as JSON for processing
    with open(output_json, 'w') as f:
        json.dump(searches, f, indent=2)

    print(f"Created {len(searches)} LinkedIn search tasks")
    print(f"Saved to: {output_json}")

    return searches


def import_results(results_file: str, db_update_sql: str = None):
    """
    Import found LinkedIn URLs and generate SQL to update database.
    """
    with open(results_file, 'r') as f:
        results = json.load(f)

    found = 0
    sql_statements = []

    for result in results:
        if result.get('found_url'):
            found += 1
            # Generate SQL update statement
            # Note: This is template - actual implementation would use ORM

    print(f"\nFound {found} out of {len(results)} LinkedIn profiles")

    if db_update_sql and found > 0:
        with open(db_update_sql, 'w') as f:
            for stmt in sql_statements:
                f.write(stmt + '\n')

        print(f"SQL updates saved to: {db_update_sql}")


if __name__ == '__main__':
    input_csv = '/tmp/decision_makers_linkedin_search.csv'
    output_json = '/tmp/linkedin_search_batch.json'

    print("Creating LinkedIn search batch...\n")
    searches = create_batch_search_file(input_csv, output_json)

    print(f"\nTop 10 searches to prioritize:\n")
    for s in searches[:10]:
        print(f"  {s['name']} @ {s['company']}")
        print(f"    Query: {s['search_query']}")
        print()
