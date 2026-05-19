"""
SQLite tracker for the LinkedIn automation pipeline.

All state - prospects, events, sessions - lives here. The runner queries
this module for what to do next and writes back what happened.

Single source of truth. No other module talks to the DB directly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from . import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    discovered_at DATETIME,
    connected_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_discovery_status ON prospects(discovery_status, country_code);
CREATE INDEX IF NOT EXISTS idx_connection_status ON prospects(connection_status, country_code);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER,
    session_id INTEGER,
    event_type TEXT NOT NULL,
    detail TEXT,
    screenshot_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(prospect_id) REFERENCES prospects(id),
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_events_prospect ON events(prospect_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, created_at);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_type TEXT NOT NULL,
    country_code TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    prospects_processed INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS dm_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Who we're messaging
    linkedin_person_url TEXT,
    linkedin_person_name TEXT NOT NULL,
    company TEXT,
    title TEXT,

    -- Context fed to Claude for generation
    profile_context TEXT,
    conversation_history TEXT,
    extra_context TEXT,
    sequence_stage TEXT DEFAULT 'm1',

    -- Generated content
    generated_message TEXT NOT NULL,

    -- Human approval gate: 0=pending, 1=approved, -1=rejected
    approved INTEGER DEFAULT 0,
    approval_note TEXT,

    -- Delivery
    status TEXT DEFAULT 'draft',
    sent_at DATETIME,
    error TEXT,
    attempts INTEGER DEFAULT 0,
    screenshot_path TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dm_status ON dm_messages(status, created_at);
CREATE INDEX IF NOT EXISTS idx_dm_person ON dm_messages(linkedin_person_name, created_at);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _ensure_dirs():
    """Create data directories if they don't exist."""
    config.HOME_DIR.mkdir(parents=True, exist_ok=True)
    config.CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with sensible defaults."""
    _ensure_dirs()
    conn = sqlite3.connect(
        str(config.DB_PATH),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Context manager for atomic DB writes."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create schema. Safe to run multiple times."""
    _ensure_dirs()
    with transaction() as conn:
        conn.executescript(SCHEMA_SQL)
    logger.info(f"Database initialized at {config.DB_PATH}")


# ---------------------------------------------------------------------------
# Prospect operations
# ---------------------------------------------------------------------------

def _external_id(business_name: str, email: str, city: str) -> str:
    """Stable hash key for dedup across re-imports."""
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
    """
    Insert or update a prospect. Returns (prospect_id, was_inserted).

    Idempotent: re-importing the same CSV will not duplicate rows.
    """
    ext_id = _external_id(business_name, email, city)
    with transaction() as conn:
        cur = conn.execute("SELECT id FROM prospects WHERE external_id = ?", (ext_id,))
        row = cur.fetchone()
        if row:
            # Update non-null fields only (don't wipe existing data with empty CSV cells)
            conn.execute(
                """
                UPDATE prospects SET
                    email = COALESCE(NULLIF(?, ''), email),
                    phone = COALESCE(NULLIF(?, ''), phone),
                    website = COALESCE(NULLIF(?, ''), website),
                    city = COALESCE(NULLIF(?, ''), city),
                    region = COALESCE(NULLIF(?, ''), region),
                    segment = COALESCE(NULLIF(?, ''), segment),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (email, phone, website, city, region, segment, row["id"]),
            )
            return row["id"], False
        cur = conn.execute(
            """
            INSERT INTO prospects
                (external_id, business_name, email, phone, website, city, region, country_code, segment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ext_id, business_name, email, phone, website, city, region, country_code, segment),
        )
        return cur.lastrowid, True


def get_prospect(prospect_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,))
        return cur.fetchone()
    finally:
        conn.close()


def get_pending_discovery(country_code: str, limit: int) -> list[sqlite3.Row]:
    """Prospects that still need their LinkedIn profile discovered."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT * FROM prospects
            WHERE country_code = ?
              AND discovery_status = 'pending'
              AND discovery_attempts < ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (country_code, config.MAX_RETRY_ATTEMPTS, limit),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_pending_connection(country_code: str, limit: int) -> list[sqlite3.Row]:
    """Prospects that have a LinkedIn URL but no connection request sent yet."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT * FROM prospects
            WHERE country_code = ?
              AND discovery_status = 'done'
              AND connection_status = 'pending'
              AND connection_attempts < ?
              AND linkedin_person_url IS NOT NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (country_code, config.MAX_RETRY_ATTEMPTS, limit),
        )
        return cur.fetchall()
    finally:
        conn.close()


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
    """Record outcome of a discovery attempt."""
    with transaction() as conn:
        conn.execute(
            """
            UPDATE prospects SET
                discovery_status = ?,
                linkedin_company_url = COALESCE(NULLIF(?, ''), linkedin_company_url),
                linkedin_company_id = COALESCE(NULLIF(?, ''), linkedin_company_id),
                linkedin_person_url = COALESCE(NULLIF(?, ''), linkedin_person_url),
                linkedin_person_name = COALESCE(NULLIF(?, ''), linkedin_person_name),
                linkedin_person_title = COALESCE(NULLIF(?, ''), linkedin_person_title),
                discovery_attempts = discovery_attempts + 1,
                last_discovery_error = ?,
                discovered_at = CASE WHEN ? = 'done' THEN CURRENT_TIMESTAMP ELSE discovered_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, company_url, company_id, person_url, person_name, person_title,
             error, status, prospect_id),
        )


def update_connection(prospect_id: int, status: str, *, error: str = "") -> None:
    """Record outcome of a connection attempt."""
    with transaction() as conn:
        conn.execute(
            """
            UPDATE prospects SET
                connection_status = ?,
                connection_attempts = connection_attempts + 1,
                last_connection_error = ?,
                connected_at = CASE WHEN ? = 'sent' THEN CURRENT_TIMESTAMP ELSE connected_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
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
    """Append-only event log. Call BEFORE the action, not after."""
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO events (prospect_id, session_id, event_type, detail, screenshot_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prospect_id, session_id, event_type, json.dumps(detail) if detail else None, screenshot_path),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------

def start_session(session_type: str, country_code: str) -> int:
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (session_type, country_code) VALUES (?, ?)",
            (session_type, country_code),
        )
        return cur.lastrowid


def end_session(
    session_id: int,
    *,
    processed: int = 0,
    successes: int = 0,
    errors: int = 0,
    blocked: bool = False,
    notes: str = "",
) -> None:
    with transaction() as conn:
        conn.execute(
            """
            UPDATE sessions SET
                ended_at = CURRENT_TIMESTAMP,
                prospects_processed = ?,
                success_count = ?,
                error_count = ?,
                blocked = ?,
                notes = ?
            WHERE id = ?
            """,
            (processed, successes, errors, 1 if blocked else 0, notes, session_id),
        )


# ---------------------------------------------------------------------------
# Stats (for dashboard + CLI status)
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
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(discovery_status='done') as d_done,
                SUM(discovery_status='pending') as d_pending,
                SUM(discovery_status='not_found') as d_nf,
                SUM(discovery_status='needs_review') as d_review,
                SUM(connection_status='sent') as c_sent,
                SUM(connection_status='pending') as c_pending,
                SUM(connection_status='already_connected') as c_already,
                SUM(connection_status='blocked') as c_blocked,
                SUM(connection_status='error') as c_error
            FROM prospects WHERE country_code = ?
            """,
            (country_code,),
        )
        row = cur.fetchone()
        return CountryStats(
            country_code=country_code,
            total=row["total"] or 0,
            discovery_done=row["d_done"] or 0,
            discovery_pending=row["d_pending"] or 0,
            discovery_not_found=row["d_nf"] or 0,
            discovery_needs_review=row["d_review"] or 0,
            connection_sent=row["c_sent"] or 0,
            connection_pending=row["c_pending"] or 0,
            connection_already_connected=row["c_already"] or 0,
            connection_blocked=row["c_blocked"] or 0,
            connection_error=row["c_error"] or 0,
        )
    finally:
        conn.close()


def weekly_invite_count() -> int:
    """How many connection requests have we sent in the last 7 days?"""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM prospects
            WHERE connection_status = 'sent'
              AND connected_at >= datetime('now', '-7 days')
            """
        )
        return cur.fetchone()["cnt"] or 0
    finally:
        conn.close()


def daily_invite_count() -> int:
    """How many connection requests have we sent today?"""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM prospects
            WHERE connection_status = 'sent'
              AND date(connected_at) = date('now')
            """
        )
        return cur.fetchone()["cnt"] or 0
    finally:
        conn.close()


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
    """Insert a new DM draft. Returns the dm_messages.id."""
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO dm_messages
                (linkedin_person_url, linkedin_person_name, company, title,
                 profile_context, conversation_history, extra_context,
                 sequence_stage, generated_message, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
            """,
            (linkedin_person_url, linkedin_person_name, company, title,
             profile_context, conversation_history, extra_context,
             sequence_stage, generated_message),
        )
        return cur.lastrowid


def approve_dm(dm_id: int, note: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE dm_messages SET approved=1, status='approved', approval_note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (note, dm_id),
        )


def reject_dm(dm_id: int, note: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE dm_messages SET approved=-1, status='rejected', approval_note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (note, dm_id),
        )


def update_dm_sent(dm_id: int, *, screenshot_path: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            """
            UPDATE dm_messages SET
                status='sent', sent_at=CURRENT_TIMESTAMP,
                attempts=attempts+1, screenshot_path=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (screenshot_path, dm_id),
        )


def update_dm_error(dm_id: int, error: str, *, screenshot_path: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            """
            UPDATE dm_messages SET
                status='error', error=?, attempts=attempts+1,
                screenshot_path=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (error, screenshot_path, dm_id),
        )


def get_dm(dm_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM dm_messages WHERE id=?", (dm_id,)).fetchone()
    finally:
        conn.close()


def get_pending_dms(limit: int = 20) -> list[sqlite3.Row]:
    """Approved DMs waiting to be sent."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM dm_messages WHERE status='approved' ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def recent_dms(limit: int = 20) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM dm_messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()


def recent_events(limit: int = 50) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT e.*, p.business_name, p.country_code
            FROM events e
            LEFT JOIN prospects p ON p.id = e.prospect_id
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()
    finally:
        conn.close()
