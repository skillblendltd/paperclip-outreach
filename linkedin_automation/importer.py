"""
CSV importer for the LinkedIn automation pipeline.

Maps Google Maps scraper CSV format to our prospect schema.
Idempotent - safe to re-run on the same CSV.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from . import db

logger = logging.getLogger(__name__)


# Map from Google Maps scraper CSV columns to our schema
COLUMN_MAP = {
    "business_name": ["business_name", "company_name", "name"],
    "email": ["email"],
    "phone": ["phone", "phone_number"],
    "website": ["website", "url"],
    "city": ["city"],
    "region": ["region", "country"],
    "segment": ["segment", "category", "business_category"],
}


def _read_field(row: dict, target: str) -> str:
    """Try each candidate column name for a target field."""
    for src in COLUMN_MAP.get(target, [target]):
        if src in row and row[src]:
            return row[src].strip()
    return ""


def import_csv(csv_path: str | Path, country_code: str) -> dict:
    """
    Import prospects from a CSV file.

    Args:
        csv_path: Path to CSV file
        country_code: ISO country code (e.g., "IE", "GB")

    Returns: Stats dict with counts.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    inserted = 0
    updated = 0
    skipped = 0
    errors = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            try:
                business_name = _read_field(row, "business_name")
                if not business_name:
                    skipped += 1
                    continue

                _, was_inserted = db.upsert_prospect(
                    business_name=business_name,
                    country_code=country_code,
                    email=_read_field(row, "email"),
                    phone=_read_field(row, "phone"),
                    website=_read_field(row, "website"),
                    city=_read_field(row, "city"),
                    region=_read_field(row, "region"),
                    segment=_read_field(row, "segment"),
                )
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1

            except Exception as e:
                logger.error(f"Row {i} failed: {e}")
                errors += 1

    stats = {
        "csv": str(csv_path),
        "country": country_code,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total": inserted + updated,
    }
    logger.info(f"Import complete: {stats}")
    return stats
