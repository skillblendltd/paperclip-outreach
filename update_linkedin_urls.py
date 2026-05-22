#!/usr/bin/env python3
"""
Update database with found LinkedIn URLs.
Use this after running WebSearch queries.
"""

import os
import django
import csv
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'outreach.settings')
django.setup()

from campaigns.models import Prospect

def update_linkedin_urls_from_csv(csv_file: str, dry_run: bool = True):
    """
    Read LinkedIn URLs from CSV and update prospects in database.

    CSV format:
    email, decision_maker_name, linkedin_url
    """
    updated = 0
    not_found = 0

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            email = row.get('email', '').strip()
            linkedin_url = row.get('linkedin_url', '').strip()
            dm_name = row.get('decision_maker_name', '').strip()

            if not email or not linkedin_url:
                continue

            try:
                prospect = Prospect.objects.get(email=email)

                print(f"✓ {prospect.business_name} ({email})")
                print(f"  Found: {dm_name} -> {linkedin_url}")

                if not dry_run:
                    prospect.linkedin_url = linkedin_url
                    prospect.save(update_fields=['linkedin_url'])
                    updated += 1
                else:
                    updated += 1

            except Prospect.DoesNotExist:
                print(f"✗ Not found in DB: {email}")
                not_found += 1

    print(f"\n✓ Updated: {updated}")
    print(f"✗ Not found: {not_found}")

    if dry_run:
        print("\n(Dry run - no changes made)")


def export_search_batch(output_csv: str, batch_size: int = 50):
    """
    Export prospects without LinkedIn URLs for batch searching.
    """
    prospects = Prospect.objects.filter(
        email__iendswith='.ie',
        linkedin_url=''
    ).order_by('business_name')[:batch_size]

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'email', 'business_name', 'decision_maker_name',
            'decision_maker_title', 'city', 'search_query'
        ])
        writer.writeheader()

        for p in prospects:
            dm_name = p.decision_maker_name or p.business_name
            search_q = f'site:linkedin.com/in/ "{dm_name}" {p.city}'

            writer.writerow({
                'email': p.email,
                'business_name': p.business_name,
                'decision_maker_name': p.decision_maker_name,
                'decision_maker_title': p.decision_maker_title,
                'city': p.city,
                'search_query': search_q
            })

    print(f"Exported {prospects.count()} Irish prospects to: {output_csv}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python manage.py update_linkedin_urls.py export <output.csv>")
        print("  python manage.py update_linkedin_urls.py update <input.csv> [--apply]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'export':
        output = sys.argv[2] if len(sys.argv) > 2 else '/tmp/irish_print_search.csv'
        export_search_batch(output)

    elif cmd == 'update':
        input_csv = sys.argv[2]
        dry_run = '--apply' not in sys.argv
        update_linkedin_urls_from_csv(input_csv, dry_run=dry_run)
        print("\nTo apply changes, re-run with --apply flag")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
