"""
PostgreSQL tracker for the LinkedIn automation pipeline.

All state - prospects, events, sessions, dm_messages - lives here.
Tables are prefixed `li_` to coexist safely with the Django campaigns schema.

Connection priority:
  1. LINKEDIN_DATABASE_URL env var (set this locally to SSH-tunnel into EC2)
  2. DATABASE_URL env var (same connection string the Django app uses)

Single source of truth. No other module talks to the DB directly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _get_dsn() -> str:
    url = os.environ.get("LINKEDIN_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No database URL found. Set LINKEDIN_DATABASE_URL or DATABASE_URL.\n"
            "To use EC2 DB locally, open an SSH tunnel first:\n"
            "  ssh -i ~/.ssh/paperclip-eu.pem -L 5434:localhost:5433 ec2-user@54.220.116.228 -N\n"
            "Then set: LINKEDIN_DATABASE_URL=postgres://outreach:localdev@localhost:5434/outreach"
        )
    return url


def _load_dotenv():
    """Load .env from repo root if present (for local runs outside Docker)."""
    import pathlib
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


_dotenv_loaded = False


def get_connection():
    """Get a psycopg2 connection. Caller is responsible for closing."""
    global _dotenv_loaded
    if not _dotenv_loaded:
        _load_dotenv()
        _dotenv_loaded = True

    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(_get_dsn())
    conn.autocommit = False
    return conn


@contextmanager
def transaction() -> Iterator:
    """Context manager for atomic DB writes. Yields a cursor."""
    conn = get_connection()
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _query(sql: str, params=()) -> list[dict]:
    """Run a SELECT and return list of dicts."""
    conn = get_connection()
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _query_one(sql: str, params=()) -> Optional[dict]:
    rows = _query(sql, params)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS li_prospects (
        id SERIAL PRIMARY KEY,
        external_id TEXT UNIQUE NOT NULL,
        business_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        website TEXT,
        city TEXT,
        region TEXT,
        country_code TEXT NOT NULL,
        segment TEXT,

        linkedin_company_url TEXT,
        linkedin_company_id TEXT,
        linkedin_person_url TEXT,
        linkedin_person_name TEXT,
        linkedin_person_title TEXT,

        discovery_status TEXT DEFAULT 'pending',
        connection_status TEXT DEFAULT 'pending',

        discovery_attempts INTEGER DEFAULT 0,
        connection_attempts INTEGER DEFAULT 0,
        last_discovery_error TEXT,
        last_connection_error TEXT,

        discovered_at TIMESTAMP,
        connected_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_li_discovery_status ON li_prospects(discovery_status, country_code)",
    "CREATE INDEX IF NOT EXISTS idx_li_connection_status ON li_prospects(connection_status, country_code)",

    """
    CREATE TABLE IF NOT EXISTS li_events (
        id SERIAL PRIMARY KEY,
        prospect_id INTEGER,
        session_id INTEGER,
        event_type TEXT NOT NULL,
        detail TEXT,
        screenshot_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_li_events_prospect ON li_events(prospect_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_li_events_session ON li_events(session_id, created_at)",

    """
    CREATE TABLE IF NOT EXISTS li_sessions (
        id SERIAL PRIMARY KEY,
        session_type TEXT NOT NULL,
        country_code TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        prospects_processed INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        error_count INTEGER DEFAULT 0,
        blocked INTEGER DEFAULT 0,
        notes TEXT
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS li_dm_messages (
        id SERIAL PRIMARY KEY,

        linkedin_person_url TEXT,
        linkedin_person_name TEXT NOT NULL,
        company TEXT,
        title TEXT,

        profile_context TEXT,
        conversation_history TEXT,
        extra_context TEXT,
        sequence_stage TEXT DEFAULT 'm1',

        generated_message TEXT NOT NULL,

        approved INTEGER DEFAULT 0,
        approval_note TEXT,

        status TEXT DEFAULT 'draft',
        sent_at TIMESTAMP,
        error TEXT,
        attempts INTEGER DEFAULT 0,
        screenshot_path TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_li_dm_status ON li_dm_messages(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_li_dm_person ON li_dm_messages(linkedin_person_name, created_at)",
]


def init_db() -> None:
    """Create all li_* tables. Safe to run multiple times."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        for stmt in _SCHEMA_STATEMENTS:
            cur.execute(stmt)
        conn.commit()
        logger.info("li_* tables initialised in PostgreSQL")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Prospect operations
# ---------------------------------------------------------------------------

def _external_id(business_name: str, email: str, city: str) -> str:
    raw = f"{business_name.lower().strip()}|{(email or '').lower().strip()}|{(city or '').lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def upsert_prospect(
    business_name: str,
    country_code: str,
    *,
    email: str = "",
    phone: str = "",
    website: str = "",
    city: str = "",
    region: str = "",
    segment: str = "",
) -> tuple[int, bool]:
    ext_id = _external_id(business_name, email, city)
    with transaction() as cur:
        cur.execute("SELECT id FROM li_prospects WHERE external_id = %s", (ext_id,))
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE li_prospects SET
                    email = COALESCE(NULLIF(%s, ''), email),
                    phone = COALESCE(NULLIF(%s, ''), phone),
                    website = COALESCE(NULLIF(%s, ''), website),
                    city = COALESCE(NULLIF(%s, ''), city),
                    region = COALESCE(NULLIF(%s, ''), region),
                    segment = COALESCE(NULLIF(%s, ''), segment),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (email, phone, website, city, region, segment, row["id"]),
            )
            return row["id"], False
        cur.execute(
            """
            INSERT INTO li_prospects
                (external_id, business_name, email, phone, website, city, region, country_code, segment)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (ext_id, business_name, email, phone, website, city, region, country_code, segment),
        )
        return cur.fetchone()["id"], True


def get_prospect(prospect_id: int) -> Optional[dict]:
    return _query_one("SELECT * FROM li_prospects WHERE id = %s", (prospect_id,))


def get_pending_discovery(country_code: str, limit: int) -> list[dict]:
    return _query(
        """
        SELECT * FROM li_prospects
        WHERE country_code = %s
          AND discovery_status = 'pending'
          AND discovery_attempts < %s
        ORDER BY id ASC
        LIMIT %s
        """,
        (country_code, 3, limit),
    )


def get_pending_connection(country_code: str, limit: int) -> list[dict]:
    return _query(
        """
        SELECT * FROM li_prospects
        WHERE country_code = %s
          AND discovery_status = 'done'
          AND connection_status = 'pending'
          AND connection_attempts < %s
          AND linkedin_person_url IS NOT NULL
        ORDER BY id ASC
        LIMIT %s
        """,
        (country_code, 3, limit),
    )


def update_discovery(
    prospect_id: int,
    status: str,
    *,
    company_url: str = "",
    company_id: str = "",
    person_url: str = "",
    person_name: str = "",
    person_title: str = "",
    error: str = "",
) -> None:
    with transaction() as cur:
        cur.execute(
            """
            UPDATE li_prospects SET
                discovery_status = %s,
                linkedin_company_url = COALESCE(NULLIF(%s, ''), linkedin_company_url),
                linkedin_company_id = COALESCE(NULLIF(%s, ''), linkedin_company_id),
                linkedin_person_url = COALESCE(NULLIF(%s, ''), linkedin_person_url),
                linkedin_person_name = COALESCE(NULLIF(%s, ''), linkedin_person_name),
                linkedin_person_title = COALESCE(NULLIF(%s, ''), linkedin_person_title),
                discovery_attempts = discovery_attempts + 1,
                last_discovery_error = %s,
                discovered_at = CASE WHEN %s = 'done' THEN CURRENT_TIMESTAMP ELSE discovered_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, company_url, company_id, person_url, person_name, person_title,
             error, status, prospect_id),
        )


def update_connection(prospect_id: int, status: str, *, error: str = "") -> None:
    with transaction() as cur:
        cur.execute(
            """
            UPDATE li_prospects SET
                connection_status = %s,
                connection_attempts = connection_attempts + 1,
                last_connection_error = %s,
                connected_at = CASE WHEN %s = 'sent' THEN CURRENT_TIMESTAMP ELSE connected_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, error, status, prospect_id),
        )


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

def log_event(
    event_type: str,
    *,
    prospect_id: Optional[int] = None,
    session_id: Optional[int] = None,
    detail: Optional[dict] = None,
    screenshot_path: str = "",
) -> int:
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO li_events (prospect_id, session_id, event_type, detail, screenshot_path)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (prospect_id, session_id, event_type,
             json.dumps(detail) if detail else None, screenshot_path),
        )
        return cur.fetchone()["id"]


# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------

def start_session(session_type: str, country_code: str) -> int:
    with transaction() as cur:
        cur.execute(
            "INSERT INTO li_sessions (session_type, country_code) VALUES (%s, %s) RETURNING id",
            (session_type, country_code),
        )
        return cur.fetchone()["id"]


def end_session(
    session_id: int,
    *,
    processed: int = 0,
    successes: int = 0,
    errors: int = 0,
    blocked: bool = False,
    notes: str = "",
) -> None:
    with transaction() as cur:
        cur.execute(
            """
            UPDATE li_sessions SET
                ended_at = CURRENT_TIMESTAMP,
                prospects_processed = %s,
                success_count = %s,
                error_count = %s,
                blocked = %s,
                notes = %s
            WHERE id = %s
            """,
            (processed, successes, errors, 1 if blocked else 0, notes, session_id),
        )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class CountryStats:
    country_code: str
    total: int
    discovery_done: int
    discovery_pending: int
    discovery_not_found: int
    discovery_needs_review: int
    connection_sent: int
    connection_pending: int
    connection_already_connected: int
    connection_blocked: int
    connection_error: int


def country_stats(country_code: str) -> CountryStats:
    row = _query_one(
        """
        SELECT
            COUNT(*) as total,
            SUM((discovery_status='done')::int) as d_done,
            SUM((discovery_status='pending')::int) as d_pending,
            SUM((discovery_status='not_found')::int) as d_nf,
            SUM((discovery_status='needs_review')::int) as d_review,
            SUM((connection_status='sent')::int) as c_sent,
            SUM((connection_status='pending')::int) as c_pending,
            SUM((connection_status='already_connected')::int) as c_already,
            SUM((connection_status='blocked')::int) as c_blocked,
            SUM((connection_status='error')::int) as c_error
        FROM li_prospects WHERE country_code = %s
        """,
        (country_code,),
    ) or {}
    return CountryStats(
        country_code=country_code,
        total=row.get("total") or 0,
        discovery_done=row.get("d_done") or 0,
        discovery_pending=row.get("d_pending") or 0,
        discovery_not_found=row.get("d_nf") or 0,
        discovery_needs_review=row.get("d_review") or 0,
        connection_sent=row.get("c_sent") or 0,
        connection_pending=row.get("c_pending") or 0,
        connection_already_connected=row.get("c_already") or 0,
        connection_blocked=row.get("c_blocked") or 0,
        connection_error=row.get("c_error") or 0,
    )


def weekly_invite_count() -> int:
    row = _query_one(
        """
        SELECT COUNT(*) as cnt FROM li_prospects
        WHERE connection_status = 'sent'
          AND connected_at >= NOW() - INTERVAL '7 days'
        """
    )
    return (row or {}).get("cnt") or 0


def daily_invite_count() -> int:
    row = _query_one(
        """
        SELECT COUNT(*) as cnt FROM li_prospects
        WHERE connection_status = 'sent'
          AND DATE(connected_at) = CURRENT_DATE
        """
    )
    return (row or {}).get("cnt") or 0


def recent_events(limit: int = 50) -> list[dict]:
    return _query(
        """
        SELECT e.*, p.business_name, p.country_code
        FROM li_events e
        LEFT JOIN li_prospects p ON p.id = e.prospect_id
        ORDER BY e.id DESC
        LIMIT %s
        """,
        (limit,),
    )


# ---------------------------------------------------------------------------
# DM message CRUD
# ---------------------------------------------------------------------------

def create_dm(
    *,
    linkedin_person_name: str,
    generated_message: str,
    linkedin_person_url: str = "",
    company: str = "",
    title: str = "",
    profile_context: str = "",
    conversation_history: str = "",
    extra_context: str = "",
    sequence_stage: str = "m1",
) -> int:
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO li_dm_messages
                (linkedin_person_url, linkedin_person_name, company, title,
                 profile_context, conversation_history, extra_context,
                 sequence_stage, generated_message, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft')
            RETURNING id
            """,
            (linkedin_person_url, linkedin_person_name, company, title,
             profile_context, conversation_history, extra_context,
             sequence_stage, generated_message),
        )
        return cur.fetchone()["id"]


def approve_dm(dm_id: int, note: str = "") -> None:
    with transaction() as cur:
        cur.execute(
            "UPDATE li_dm_messages SET approved=1, status='approved', approval_note=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (note, dm_id),
        )


def reject_dm(dm_id: int, note: str = "") -> None:
    with transaction() as cur:
        cur.execute(
            "UPDATE li_dm_messages SET approved=-1, status='rejected', approval_note=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (note, dm_id),
        )


def update_dm_sent(dm_id: int, *, screenshot_path: str = "") -> None:
    with transaction() as cur:
        cur.execute(
            """
            UPDATE li_dm_messages SET
                status='sent', sent_at=CURRENT_TIMESTAMP,
                attempts=attempts+1, screenshot_path=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (screenshot_path, dm_id),
        )


def update_dm_error(dm_id: int, error: str, *, screenshot_path: str = "") -> None:
    with transaction() as cur:
        cur.execute(
            """
            UPDATE li_dm_messages SET
                status='error', error=%s, attempts=attempts+1,
                screenshot_path=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (error, screenshot_path, dm_id),
        )


def get_dm(dm_id: int) -> Optional[dict]:
    return _query_one("SELECT * FROM li_dm_messages WHERE id = %s", (dm_id,))


def get_pending_dms(limit: int = 20) -> list[dict]:
    return _query(
        "SELECT * FROM li_dm_messages WHERE status='approved' ORDER BY created_at ASC LIMIT %s",
        (limit,),
    )


def recent_dms(limit: int = 20) -> list[dict]:
    return _query(
        "SELECT * FROM li_dm_messages ORDER BY id DESC LIMIT %s", (limit,)
    )
