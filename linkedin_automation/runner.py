"""
The Runner.

Orchestrates a single session of discovery or connection work:
- Pulls pending prospects from DB
- Calls the appropriate module (search or connect)
- Records outcomes back to DB
- Enforces pacing (per-action delays + mid-session pauses)
- Enforces caps (daily, weekly)
- Trips the circuit breaker on LinkedIn blocks

This is the only module the CLI calls into for actual work.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from . import config, db, human

# Lazy imports - only needed when actually running a session.
# Lets `cli import/status` work without selenium installed.
def _lazy_imports():
    from .browser import Browser
    from .connect import send_connection
    from .search import discover_prospect
    return Browser, send_connection, discover_prospect

logger = logging.getLogger(__name__)


@dataclass
class SessionSummary:
    session_id: int
    session_type: str
    country_code: str
    processed: int = 0
    successes: int = 0
    errors: int = 0
    blocked: bool = False
    block_reason: str = ""
    consecutive_errors: int = 0
    daily_cap_hit: bool = False
    weekly_cap_hit: bool = False
    items: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery session
# ---------------------------------------------------------------------------

def run_discovery_session(
    country_code: str,
    batch_size: int = config.DISCOVERY_BATCH_SIZE_DEFAULT,
) -> SessionSummary:
    """
    One discovery session - find LinkedIn URLs for up to `batch_size` prospects.

    Discovery is read-only and lower risk. We can run aggressively here.
    """
    session_id = db.start_session("discovery", country_code)
    summary = SessionSummary(
        session_id=session_id,
        session_type="discovery",
        country_code=country_code,
    )

    pending = db.get_pending_discovery(country_code, batch_size)
    if not pending:
        logger.info(f"No pending discovery work for {country_code}")
        db.end_session(session_id, notes="no_work")
        return summary

    logger.info(f"Starting discovery: {len(pending)} prospects for {country_code}")

    Browser, _send_connection, discover_prospect = _lazy_imports()
    with Browser() as br:
        if not br.is_logged_in():
            db.end_session(session_id, notes="not_logged_in", blocked=True)
            summary.blocked = True
            summary.block_reason = "Not logged into LinkedIn. Run: linkedin_automation.cli login"
            return summary

        for i, prospect in enumerate(pending, 1):
            db.log_event(
                "discovery_started",
                prospect_id=prospect["id"],
                session_id=session_id,
                detail={"business_name": prospect["business_name"]},
            )

            result = discover_prospect(
                br,
                business_name=prospect["business_name"],
                city=prospect["city"] or "",
                country_code=prospect["country_code"] or "",
                website=prospect["website"] or "",
            )

            db.update_discovery(
                prospect["id"],
                status=result.status,
                company_url=result.company_url,
                person_url=result.person_url,
                person_name=result.person_name,
                person_title=result.person_title,
                error=result.error,
            )

            db.log_event(
                "discovery_done",
                prospect_id=prospect["id"],
                session_id=session_id,
                detail={
                    "status": result.status,
                    "match_score": result.match_score,
                    "domain_verified": result.domain_verified,
                    "person_url": result.person_url,
                    "person_title": result.person_title,
                    "candidates": result.candidates_considered,
                    "error": result.error,
                },
                screenshot_path=br.screenshot(f"discovery_{prospect['id']}_{result.status}")
                    if result.status in ("error", "blocked") else "",
            )

            summary.processed += 1
            summary.items.append({
                "prospect_id": prospect["id"],
                "business_name": prospect["business_name"],
                "status": result.status,
                "person": result.person_name,
                "title": result.person_title,
            })

            if result.status == "done":
                summary.successes += 1
                summary.consecutive_errors = 0
            elif result.status == "blocked":
                summary.blocked = True
                summary.block_reason = result.error
                logger.critical(f"BLOCKED by LinkedIn: {result.error}. Stopping session.")
                break
            else:
                summary.errors += 1
                if result.status == "error":
                    summary.consecutive_errors += 1
                else:
                    summary.consecutive_errors = 0  # not_found is a clean outcome

            if summary.consecutive_errors >= config.CONSECUTIVE_ERROR_LIMIT:
                logger.critical(f"{summary.consecutive_errors} consecutive errors. Stopping.")
                summary.blocked = True
                summary.block_reason = "consecutive_errors"
                break

            # Mid-session pause every N actions
            if i % config.SESSION_PAUSE_AFTER_N_ACTIONS == 0 and i < len(pending):
                logger.info(f"Mid-session pause after {i} actions")
                human.session_break()
            elif i < len(pending):
                human.discovery_pause()

    db.end_session(
        session_id,
        processed=summary.processed,
        successes=summary.successes,
        errors=summary.errors,
        blocked=summary.blocked,
        notes=summary.block_reason,
    )
    return summary


# ---------------------------------------------------------------------------
# Connection session
# ---------------------------------------------------------------------------

def run_connection_session(
    country_code: str,
    daily_cap: int = config.CONNECTION_DAILY_CAP_DEFAULT,
    dry_run: bool = False,
) -> SessionSummary:
    """
    One connection session - send connection requests up to daily_cap.

    Enforces:
    - daily_cap (per-day connections sent)
    - weekly_cap (LinkedIn's ~100/week limit)
    - circuit breaker on blocks

    Args:
        dry_run: If True, navigate to each profile and detect the Connect
            button state, but do NOT click. No invites are spent. Status
            results are prefixed 'dry_run_'. Useful for previewing what a
            real run would do.
    """
    session_type = "connection_dry_run" if dry_run else "connection"
    session_id = db.start_session(session_type, country_code)
    summary = SessionSummary(
        session_id=session_id,
        session_type=session_type,
        country_code=country_code,
    )

    # On dry-run we don't enforce caps - we're not spending invites.
    if dry_run:
        budget = daily_cap  # treat as "how many to preview"
        logger.info(f"DRY-RUN: previewing up to {budget} prospects, no invites sent.")
    else:
        # Cap budget = min of daily_cap, daily_remaining, weekly_remaining
        daily_sent = db.daily_invite_count()
        weekly_sent = db.weekly_invite_count()
        daily_remaining = max(0, daily_cap - daily_sent)
        weekly_remaining = max(0, config.CONNECTION_WEEKLY_CAP - weekly_sent)
        budget = min(daily_remaining, weekly_remaining)

        logger.info(
            f"Connection budget: daily_sent={daily_sent}/{daily_cap}, "
            f"weekly_sent={weekly_sent}/{config.CONNECTION_WEEKLY_CAP}, "
            f"budget={budget}"
        )

        if budget == 0:
            if daily_remaining == 0:
                summary.daily_cap_hit = True
                note = "daily_cap_already_hit"
            else:
                summary.weekly_cap_hit = True
                note = "weekly_cap_already_hit"
            db.end_session(session_id, notes=note)
            return summary

    pending = db.get_pending_connection(country_code, budget)
    if not pending:
        logger.info(f"No pending connections for {country_code}")
        db.end_session(session_id, notes="no_work")
        return summary

    logger.info(f"Starting connection session: {len(pending)} prospects for {country_code}")

    Browser, send_connection, _discover = _lazy_imports()
    with Browser() as br:
        if not br.is_logged_in():
            db.end_session(session_id, notes="not_logged_in", blocked=True)
            summary.blocked = True
            summary.block_reason = "Not logged into LinkedIn. Run: linkedin_automation.cli login"
            return summary

        for i, prospect in enumerate(pending, 1):
            db.log_event(
                "connect_dry_run_started" if dry_run else "connect_started",
                prospect_id=prospect["id"],
                session_id=session_id,
                detail={
                    "business_name": prospect["business_name"],
                    "person_url": prospect["linkedin_person_url"],
                    "dry_run": dry_run,
                },
            )

            result = send_connection(br, prospect["linkedin_person_url"], dry_run=dry_run)

            # On dry-run: do NOT mutate connection_status (keep as 'pending')
            # Only log the event for review.
            if not dry_run:
                db.update_connection(
                    prospect["id"],
                    status=result.status,
                    error=result.error,
                )

            db.log_event(
                "connect_dry_run_done" if dry_run else "connect_done",
                prospect_id=prospect["id"],
                session_id=session_id,
                detail={"status": result.status, "error": result.error, "dry_run": dry_run},
                screenshot_path=br.screenshot(
                    f"{'dryrun' if dry_run else 'connect'}_{prospect['id']}_{result.status}"
                ),  # always screenshot dry-run so we can audit
            )

            summary.processed += 1
            summary.items.append({
                "prospect_id": prospect["id"],
                "business_name": prospect["business_name"],
                "person": prospect["linkedin_person_name"],
                "status": result.status,
            })

            # Success classifier: real run vs dry-run have different "good" statuses
            success_statuses = {"sent"} if not dry_run else {"dry_run_ready", "dry_run_ready_via_more"}
            # email_required = LinkedIn blocked due to out-of-network; not our bug, reset streak
            clean_outcome_statuses = {"already_connected", "email_required", "not_found"} if not dry_run else {
                "dry_run_already_connected", "dry_run_pending", "dry_run_not_found", "dry_run_no_button",
            }

            if result.status in success_statuses:
                summary.successes += 1
                summary.consecutive_errors = 0
            elif result.status == "blocked":
                summary.blocked = True
                summary.block_reason = result.error
                logger.critical(f"BLOCKED by LinkedIn: {result.error}. Stopping.")
                break
            elif result.status in clean_outcome_statuses:
                summary.consecutive_errors = 0  # clean outcome
            else:
                summary.errors += 1
                if result.status == "error":
                    summary.consecutive_errors += 1
                else:
                    summary.consecutive_errors = 0

            if summary.consecutive_errors >= config.CONSECUTIVE_ERROR_LIMIT:
                logger.critical(f"{summary.consecutive_errors} consecutive errors. Stopping.")
                summary.blocked = True
                summary.block_reason = "consecutive_errors"
                break

            # Pacing
            if i % config.SESSION_PAUSE_AFTER_N_ACTIONS == 0 and i < len(pending):
                logger.info(f"Mid-session break after {i} connections")
                human.session_break()
            elif i < len(pending):
                human.connection_pause()

    db.end_session(
        session_id,
        processed=summary.processed,
        successes=summary.successes,
        errors=summary.errors,
        blocked=summary.blocked,
        notes=summary.block_reason,
    )
    return summary
