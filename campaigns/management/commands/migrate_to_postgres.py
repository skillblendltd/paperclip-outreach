"""
One-time migration: SQLite -> PostgreSQL
Reads from SQLite (hardcoded path), writes to current default DB (must be PG).
Preserves UUIDs, timestamps, all relationships.

Usage:
    python manage.py migrate_to_postgres                  # Run migration
    python manage.py migrate_to_postgres --verify-only    # Just compare row counts
    python manage.py migrate_to_postgres --truncate       # Truncate PG before import
"""
import sqlite3
import sys
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.conf import settings
from django.apps import apps


def convert_row(row, bool_columns):
    """Convert SQLite row values to PostgreSQL-compatible types."""
    converted = []
    for i, val in enumerate(row):
        if i in bool_columns and val is not None:
            # SQLite stores bools as 0/1 ints
            converted.append(bool(val))
        else:
            converted.append(val)
    return converted


def get_max_lengths(model_path, sqlite_columns):
    """Return dict of {column_index: max_length} for CharField/EmailField columns."""
    if not model_path:
        return {}
    from django.apps import apps
    from django.db import models as dj_models
    try:
        app_label, model_name = model_path.split('.')
        model = apps.get_model(app_label, model_name)
    except Exception:
        return {}

    field_max = {}
    for field in model._meta.get_fields():
        if isinstance(field, (dj_models.CharField, dj_models.EmailField, dj_models.SlugField, dj_models.URLField)):
            if hasattr(field, 'column') and field.max_length:
                field_max[field.column] = field.max_length

    result = {}
    for i, col in enumerate(sqlite_columns):
        if col in field_max:
            result[i] = field_max[col]
    return result


def truncate_row(row, max_lengths):
    """Truncate string values that exceed PG column max_length."""
    converted = list(row)
    for i, max_len in max_lengths.items():
        if converted[i] and isinstance(converted[i], str) and len(converted[i]) > max_len:
            converted[i] = converted[i][:max_len]
    return converted


def get_bool_columns_from_model(model_path, sqlite_columns):
    """Find indexes of boolean columns by looking at the Django model."""
    if not model_path:
        return set()
    from django.apps import apps
    from django.db.models import BooleanField
    try:
        app_label, model_name = model_path.split('.')
        model = apps.get_model(app_label, model_name)
    except Exception:
        return set()

    bool_field_names = set()
    for field in model._meta.get_fields():
        if isinstance(field, BooleanField):
            bool_field_names.add(field.column)

    bool_cols = set()
    for i, col in enumerate(sqlite_columns):
        if col in bool_field_names:
            bool_cols.add(i)
    return bool_cols


SQLITE_PATH = Path(settings.BASE_DIR) / 'db' / 'outreach.sqlite3'

# Order matters - foreign keys first
TABLE_ORDER = [
    ('auth_user', None),  # Django built-in
    ('organizations', 'campaigns.Organization'),
    ('products', 'campaigns.Product'),
    ('campaigns', 'campaigns.Campaign'),
    ('mailbox_configs', 'campaigns.MailboxConfig'),
    ('prospects', 'campaigns.Prospect'),
    ('email_log', 'campaigns.EmailLog'),
    ('email_queue', 'campaigns.EmailQueue'),
    ('call_log', 'campaigns.CallLog'),
    ('inbound_emails', 'campaigns.InboundEmail'),
    ('reply_templates', 'campaigns.ReplyTemplate'),
    ('suppressions', 'campaigns.Suppression'),
    ('script_insights', 'campaigns.ScriptInsight'),
    ('email_templates', 'campaigns.EmailTemplate'),
    ('call_scripts', 'campaigns.CallScript'),
    ('prompt_templates', 'campaigns.PromptTemplate'),
    ('ai_usage_log', 'campaigns.AIUsageLog'),
]


class Command(BaseCommand):
    help = 'Migrate data from SQLite to PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument('--verify-only', action='store_true', help='Just compare row counts')
        parser.add_argument('--truncate', action='store_true', help='Truncate PG tables first')

    def handle(self, *args, **options):
        verify_only = options['verify_only']
        truncate = options['truncate']

        # Verify we're connected to PostgreSQL
        if connection.vendor != 'postgresql':
            self.stderr.write(self.style.ERROR(
                f'Default DB is {connection.vendor}, not postgresql! '
                f'Set DATABASE_URL=postgres://... in .env first.'
            ))
            sys.exit(1)

        if not SQLITE_PATH.exists():
            self.stderr.write(self.style.ERROR(f'SQLite file not found: {SQLITE_PATH}'))
            sys.exit(1)

        self.stdout.write(f'Source SQLite: {SQLITE_PATH}')
        self.stdout.write(f'Target PG: {connection.settings_dict["NAME"]}@{connection.settings_dict.get("HOST", "?")}')
        self.stdout.write('')

        sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
        sqlite_conn.row_factory = sqlite3.Row

        # Phase 1: Compare row counts
        self.stdout.write('=== ROW COUNT COMPARISON ===')
        sqlite_counts = {}
        pg_counts = {}
        for table_name, model_path in TABLE_ORDER:
            try:
                cur = sqlite_conn.cursor()
                cur.execute(f'SELECT COUNT(*) FROM {table_name}')
                sqlite_counts[table_name] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                sqlite_counts[table_name] = 0

            try:
                with connection.cursor() as cur:
                    cur.execute(f'SELECT COUNT(*) FROM {table_name}')
                    pg_counts[table_name] = cur.fetchone()[0]
            except Exception:
                pg_counts[table_name] = 0

            sl = sqlite_counts[table_name]
            pg = pg_counts[table_name]
            mark = 'OK' if sl == pg else 'DIFF'
            self.stdout.write(f'  {table_name:30s} SQLite={sl:6d}  PG={pg:6d}  [{mark}]')

        if verify_only:
            sqlite_conn.close()
            return

        # Phase 2: Truncate if requested
        if truncate:
            self.stdout.write('\n=== TRUNCATING PG TABLES ===')
            with connection.cursor() as cur:
                # Reverse order to handle FKs
                for table_name, _ in reversed(TABLE_ORDER):
                    if table_name == 'auth_user':
                        continue
                    try:
                        cur.execute(f'TRUNCATE TABLE {table_name} CASCADE')
                        self.stdout.write(f'  Truncated {table_name}')
                    except Exception as e:
                        self.stdout.write(f'  Skip {table_name}: {e}')

        # Phase 3: Copy data
        self.stdout.write('\n=== COPYING DATA ===')
        for table_name, model_path in TABLE_ORDER:
            if table_name == 'auth_user':
                continue
            sqlite_count = sqlite_counts.get(table_name, 0)
            if sqlite_count == 0:
                self.stdout.write(f'  {table_name}: empty, skip')
                continue

            self.stdout.write(f'  {table_name}: copying {sqlite_count} rows...')

            cur = sqlite_conn.cursor()
            cur.execute(f'SELECT * FROM {table_name}')
            rows = cur.fetchall()

            if not rows:
                continue

            columns = [d[0] for d in cur.description]
            bool_cols = get_bool_columns_from_model(model_path, columns)
            max_lengths = get_max_lengths(model_path, columns)
            placeholders = ', '.join(['%s'] * len(columns))
            col_list = ', '.join(columns)
            insert_sql = f'INSERT INTO {table_name} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

            inserted = 0
            errors_shown = 0
            from django.db import connections
            pg_conn = connections['default']
            for row in rows:
                try:
                    with transaction.atomic():
                        with pg_conn.cursor() as pg_cur:
                            converted = convert_row(list(row), bool_cols)
                            converted = truncate_row(converted, max_lengths)
                            pg_cur.execute(insert_sql, converted)
                            inserted += 1
                except Exception as e:
                    if errors_shown < 5:
                        self.stderr.write(f'    Row error in {table_name}: {str(e)[:300]}')
                        errors_shown += 1
            self.stdout.write(f'    Inserted {inserted}/{len(rows)}')

        sqlite_conn.close()

        # Phase 4: Final comparison
        self.stdout.write('\n=== FINAL ROW COUNT COMPARISON ===')
        all_match = True
        for table_name, _ in TABLE_ORDER:
            try:
                cur = sqlite3.connect(str(SQLITE_PATH)).cursor()
                cur.execute(f'SELECT COUNT(*) FROM {table_name}')
                sl = cur.fetchone()[0]
            except Exception:
                sl = 0
            try:
                with connection.cursor() as pg_cur:
                    pg_cur.execute(f'SELECT COUNT(*) FROM {table_name}')
                    pg = pg_cur.fetchone()[0]
            except Exception:
                pg = 0
            mark = 'OK' if sl == pg else 'MISMATCH'
            if sl != pg:
                all_match = False
            self.stdout.write(f'  {table_name:30s} SQLite={sl:6d}  PG={pg:6d}  [{mark}]')

        if all_match:
            self.stdout.write(self.style.SUCCESS('\nAll row counts match! Migration complete.'))
        else:
            self.stderr.write(self.style.ERROR('\nROW COUNT MISMATCH! Investigate before switching.'))
