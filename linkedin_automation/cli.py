"""
CLI for the LinkedIn automation pipeline.

Uses Click for ergonomic commands. Every command is idempotent and
crash-safe; nothing in this file holds mutable state.

Usage:
    python -m linkedin_automation.cli init
    python -m linkedin_automation.cli import --csv path/to.csv --country IE
    python -m linkedin_automation.cli login
    python -m linkedin_automation.cli discover --country IE --batch-size 30
    python -m linkedin_automation.cli connect --country IE --daily-cap 30
    python -m linkedin_automation.cli status [--country IE]
    python -m linkedin_automation.cli dashboard
    python -m linkedin_automation.cli reset-stuck --type discovery
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from . import config, db, runner
from .importer import import_csv

# Configure logging once at CLI entry
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _configure_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt="%H:%M:%S")
    # Also write to file
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / "linkedin_automation.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(file_handler)


@click.group()
@click.option("--verbose", is_flag=True, help="Verbose logging")
def cli(verbose):
    """LinkedIn Connection Automation."""
    _configure_logging(verbose)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

@cli.command()
def init():
    """Initialize database and directories."""
    db.init_db()
    click.echo(f"✅ Database initialized at {config.DB_PATH}")
    click.echo(f"📂 Chrome profile dir: {config.CHROME_PROFILE_DIR}")
    click.echo(f"📂 Logs: {config.LOGS_DIR}")
    click.echo(f"📂 Screenshots: {config.SCREENSHOTS_DIR}")


@cli.command(name="import")
@click.option("--csv", "csv_path", required=True, type=click.Path(exists=True),
              help="Path to CSV file")
@click.option("--country", required=True, help="ISO country code (e.g., IE, GB)")
def import_cmd(csv_path, country):
    """Import prospects from a CSV file."""
    db.init_db()  # Idempotent
    stats = import_csv(csv_path, country.upper())
    click.echo("\n📊 Import Stats:")
    click.echo(f"  Inserted: {stats['inserted']}")
    click.echo(f"  Updated:  {stats['updated']}")
    click.echo(f"  Skipped:  {stats['skipped']}")
    click.echo(f"  Errors:   {stats['errors']}")
    click.echo(f"  Total in DB after import: {stats['total']}")


@cli.command()
def login():
    """
    Open Chrome with the persistent profile so you can log in to LinkedIn.

    First-time: log in manually with email/password (and 2FA if prompted).
    The session cookie is saved to the Chrome profile dir, so future runs
    don't need to log in again.

    Once logged in, just close the browser window. Your session is preserved.
    """
    click.echo("Opening Chrome...")
    click.echo("Log in to LinkedIn manually.")
    click.echo("When done, close the Chrome window (or press Ctrl+C here).")

    try:
        from .browser import Browser
    except RuntimeError as e:
        click.echo(f"Cannot start browser: {e}")
        sys.exit(1)
    br = Browser()
    try:
        br.start()
        br.driver.get("https://www.linkedin.com/login")
        # Keep the browser open until the user closes it
        try:
            while True:
                # Check every few seconds if the window is still open
                try:
                    _ = br.driver.current_url
                except Exception:
                    break
                import time as _time
                _time.sleep(3)
        except KeyboardInterrupt:
            pass
    finally:
        br.stop()
    click.echo("✅ Session saved. You can now run `discover` and `connect`.")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--country", required=True, help="ISO country code (e.g., IE, GB)")
@click.option("--batch-size", default=config.DISCOVERY_BATCH_SIZE_DEFAULT,
              help="Max prospects to process this session")
def discover(country, batch_size):
    """Find LinkedIn profiles for pending prospects."""
    country = country.upper()
    click.echo(f"🔍 Starting discovery session for {country} (batch_size={batch_size})")
    summary = runner.run_discovery_session(country, batch_size=batch_size)

    click.echo("\n📊 Discovery Session Summary:")
    click.echo(f"  Session ID: {summary.session_id}")
    click.echo(f"  Processed:  {summary.processed}")
    click.echo(f"  Successes:  {summary.successes}")
    click.echo(f"  Errors:     {summary.errors}")
    if summary.blocked:
        click.secho(f"  🚨 BLOCKED: {summary.block_reason}", fg="red", bold=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--country", required=True, help="ISO country code (e.g., IE, GB)")
@click.option("--daily-cap", default=config.CONNECTION_DAILY_CAP_DEFAULT,
              help="Max connections to send today")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview only: visit each profile and detect the Connect button "
                   "state, but DO NOT click anything. Zero invites sent. Use this "
                   "before the first real run to validate the matcher.")
def connect(country, daily_cap, dry_run):
    """Send connection requests for discovered prospects."""
    country = country.upper()
    mode = "DRY-RUN" if dry_run else "LIVE"
    click.echo(f"Starting connection session for {country} [{mode}] (cap={daily_cap})")
    if dry_run:
        click.echo("DRY-RUN: visiting profiles to detect Connect state. No invites will be sent.")
    summary = runner.run_connection_session(country, daily_cap=daily_cap, dry_run=dry_run)

    click.echo("\nConnection Session Summary:")
    click.echo(f"  Session ID:    {summary.session_id}")
    click.echo(f"  Processed:     {summary.processed}")
    label = "Would send" if dry_run else "Sent"
    click.echo(f"  {label}:          {summary.successes}")
    click.echo(f"  Errors:        {summary.errors}")

    # Status breakdown - critical for dry-run review
    by_status = {}
    for item in summary.items:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
    if by_status:
        click.echo("\n  Status breakdown:")
        for st, n in sorted(by_status.items(), key=lambda x: -x[1]):
            click.echo(f"    {st:35s} {n}")

    if summary.daily_cap_hit:
        click.echo("  Daily cap already reached. Try again tomorrow.")
    if summary.weekly_cap_hit:
        click.echo("  Weekly cap already reached. Try again next week.")
    if summary.blocked:
        click.secho(f"  BLOCKED: {summary.block_reason}", fg="red", bold=True)
        click.secho("  Verify your LinkedIn account health before resuming.", fg="red")
        sys.exit(2)
    if dry_run:
        click.echo(f"\n  Screenshots in: {config.SCREENSHOTS_DIR}")
        click.echo("  Review the dryrun_*.png files to confirm each match was a real person.")


# ---------------------------------------------------------------------------
# Status / monitoring
# ---------------------------------------------------------------------------

@cli.command(name="review-report")
@click.option("--country", required=True, help="ISO country code (e.g., IE)")
@click.option("--session-id", type=int, default=None,
              help="Limit to a specific discovery session. Default: most recent session.")
@click.option("--csv", "csv_path", type=click.Path(), default=None,
              help="Save as CSV for spreadsheet review")
def review_report(country, session_id, csv_path):
    """
    Show discovery results for manual correctness review.

    For each prospect, shows: CSV row -> LinkedIn match (company + person) +
    match score + domain-verified flag, so you can open both URLs and judge
    correctness.
    """
    import csv as _csv
    import json
    db.init_db()
    country = country.upper()
    conn = db.get_connection()
    try:
        # If no session specified, get the most recent discovery session for this country
        if session_id is None:
            row = conn.execute(
                """SELECT id FROM sessions
                   WHERE session_type='discovery' AND country_code=?
                   ORDER BY id DESC LIMIT 1""",
                (country,),
            ).fetchone()
            if not row:
                click.echo(f"No discovery sessions found for {country}.")
                return
            session_id = row["id"]

        # Pull all events from this session, joined with prospect data
        rows = conn.execute(
            """
            SELECT
                p.id AS prospect_id,
                p.business_name, p.email, p.city, p.region, p.website,
                p.linkedin_company_url, p.linkedin_person_url,
                p.linkedin_person_name, p.linkedin_person_title,
                p.discovery_status, p.last_discovery_error,
                e.detail AS event_detail,
                e.created_at AS event_at
            FROM events e
            JOIN prospects p ON p.id = e.prospect_id
            WHERE e.session_id = ?
              AND e.event_type = 'discovery_done'
            ORDER BY e.id ASC
            """,
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        click.echo(f"No discovery_done events in session {session_id}.")
        return

    # Tally automatic metrics
    total = len(rows)
    by_status = {}
    domain_verified = 0
    score_sum = 0
    score_count = 0
    title_quality = {"senior": 0, "other": 0, "none": 0}

    senior_keywords = {"owner", "founder", "ceo", "managing director", "director",
                       "md", "president", "head of", "vp", "co-founder", "co founder"}

    for r in rows:
        by_status[r["discovery_status"]] = by_status.get(r["discovery_status"], 0) + 1
        try:
            detail = json.loads(r["event_detail"]) if r["event_detail"] else {}
        except (TypeError, json.JSONDecodeError):
            detail = {}
        if detail.get("domain_verified"):
            domain_verified += 1
        score = detail.get("match_score")
        if score is not None:
            score_sum += score
            score_count += 1
        title = (r["linkedin_person_title"] or "").lower()
        if not title:
            title_quality["none"] += 1
        elif any(kw in title for kw in senior_keywords):
            title_quality["senior"] += 1
        else:
            title_quality["other"] += 1

    # Summary header
    click.echo(f"\n{'='*78}")
    click.echo(f"Discovery Review Report — session #{session_id} ({country})")
    click.echo(f"{'='*78}\n")
    click.echo(f"Total processed:       {total}")
    for status_name in ("done", "needs_review", "not_found", "error", "blocked"):
        n = by_status.get(status_name, 0)
        if n:
            click.echo(f"  {status_name:18s} {n:3d}  ({100*n/total:5.1f}%)")
    if score_count:
        click.echo(f"\nMean match score:      {score_sum/score_count:.1f}")
    click.echo(f"Domain verified:       {domain_verified}/{total}  ({100*domain_verified/total:.1f}%)")
    click.echo(f"\nDecision-maker title quality:")
    click.echo(f"  senior (owner/founder/CEO/director/MD/etc): {title_quality['senior']}")
    click.echo(f"  other:                                       {title_quality['other']}")
    click.echo(f"  none / not applicable:                       {title_quality['none']}")

    # Per-prospect detail
    click.echo(f"\n{'-'*78}")
    click.echo("Per-prospect detail (open the URLs and mark each as ✓ / ✗ / ?):\n")

    review_rows = []
    for i, r in enumerate(rows, 1):
        try:
            detail = json.loads(r["event_detail"]) if r["event_detail"] else {}
        except (TypeError, json.JSONDecodeError):
            detail = {}
        score = detail.get("match_score") or 0
        verified = detail.get("domain_verified", False)

        click.echo(f"[{i}] {r['business_name']}  ({r['city'] or '?'}, {r['region'] or '?'})")
        click.echo(f"     CSV website:    {r['website'] or '(none)'}")
        click.echo(f"     Status:         {r['discovery_status']}  "
                   f"(score={score}, domain_verified={'YES' if verified else 'no'})")
        if r["linkedin_company_url"]:
            click.echo(f"     LinkedIn co:    {r['linkedin_company_url']}")
        if r["linkedin_person_url"]:
            click.echo(f"     LinkedIn person: {r['linkedin_person_url']}")
            click.echo(f"     Name + title:   {r['linkedin_person_name']} — {r['linkedin_person_title']}")
        if r["last_discovery_error"]:
            click.echo(f"     Error:          {r['last_discovery_error']}")
        click.echo("")

        review_rows.append({
            "row": i,
            "prospect_id": r["prospect_id"],
            "business_name": r["business_name"],
            "csv_city": r["city"] or "",
            "csv_region": r["region"] or "",
            "csv_website": r["website"] or "",
            "csv_email": r["email"] or "",
            "discovery_status": r["discovery_status"],
            "match_score": score,
            "domain_verified": "YES" if verified else "no",
            "linkedin_company_url": r["linkedin_company_url"] or "",
            "linkedin_person_url": r["linkedin_person_url"] or "",
            "linkedin_person_name": r["linkedin_person_name"] or "",
            "linkedin_person_title": r["linkedin_person_title"] or "",
            "error": r["last_discovery_error"] or "",
            "your_verdict_correct_yes_no_unsure": "",
            "your_notes": "",
        })

    # Save CSV if requested, or auto-save to logs dir
    if csv_path is None:
        csv_path = config.LOGS_DIR / f"review_{country}_session{session_id}.csv"
    else:
        csv_path = config.LOGS_DIR.parent / csv_path if not str(csv_path).startswith("/") else csv_path

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=list(review_rows[0].keys()))
        writer.writeheader()
        writer.writerows(review_rows)

    click.echo(f"{'-'*78}")
    click.echo(f"CSV saved: {csv_path}")
    click.echo(f"\nMark verdicts in the 'your_verdict_correct_yes_no_unsure' column "
               f"and share back so we can compute the real success rate.")


@cli.command()
@click.option("--country", help="ISO country code (omit to show all)")
def status(country):
    """Show pipeline status."""
    db.init_db()  # Safe if already exists
    countries = [country.upper()] if country else _all_countries()
    if not countries:
        click.echo("No prospects imported yet.")
        return

    click.echo("\n📈 Pipeline Status\n" + "=" * 60)
    for cc in countries:
        s = db.country_stats(cc)
        click.echo(f"\n🌍 {cc} (total: {s.total})")
        click.echo(f"  Discovery: {s.discovery_done} done | {s.discovery_pending} pending | "
                   f"{s.discovery_needs_review} needs review | {s.discovery_not_found} not found")
        click.echo(f"  Connection: {s.connection_sent} sent | {s.connection_pending} pending | "
                   f"{s.connection_already_connected} already | {s.connection_error} errors")

    click.echo(f"\n⏱️  Today: {db.daily_invite_count()} connections sent")
    click.echo(f"📅 Last 7 days: {db.weekly_invite_count()} / {config.CONNECTION_WEEKLY_CAP} weekly cap")


def _all_countries():
    conn = db.get_connection()
    try:
        cur = conn.execute("SELECT DISTINCT country_code FROM prospects ORDER BY country_code")
        return [r["country_code"] for r in cur.fetchall()]
    finally:
        conn.close()


@cli.command(name="reset-stuck")
@click.option("--type", "kind", type=click.Choice(["discovery", "connection"]),
              required=True, help="Which status to reset")
@click.option("--country", help="Only reset for one country")
def reset_stuck(kind, country):
    """Reset status='error' back to 'pending' for retry."""
    db.init_db()
    column = "discovery_status" if kind == "discovery" else "connection_status"
    attempts_column = "discovery_attempts" if kind == "discovery" else "connection_attempts"

    conn = db.get_connection()
    try:
        params = []
        sql = f"UPDATE prospects SET {column}='pending', {attempts_column}=0 WHERE {column}='error'"
        if country:
            sql += " AND country_code=?"
            params.append(country.upper())
        cur = conn.execute(sql, params)
        conn.commit()
        click.echo(f"✅ Reset {cur.rowcount} stuck {kind} rows")
    finally:
        conn.close()


@cli.command()
@click.option("--country", help="ISO country code filter")
@click.option("--limit", default=50, help="Max rows to show")
def review(country, limit):
    """List prospects flagged as needs_review (ambiguous company match)."""
    db.init_db()
    conn = db.get_connection()
    try:
        sql = """
            SELECT id, business_name, city, country_code, website,
                   linkedin_company_url, last_discovery_error
            FROM prospects
            WHERE discovery_status = 'needs_review'
        """
        params = []
        if country:
            sql += " AND country_code = ?"
            params.append(country.upper())
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        click.echo("No prospects need review.")
        return

    click.echo(f"\n{len(rows)} prospects need review:\n")
    for r in rows:
        click.echo(f"  [{r['id']}] {r['business_name']}  ({r['city']}, {r['country_code']})")
        click.echo(f"       Website: {r['website']}")
        click.echo(f"       Top match: {r['linkedin_company_url']}")
        click.echo(f"       Reason: {r['last_discovery_error']}")
        click.echo()
    click.echo("To accept a match: cli accept-match --prospect-id <id> --url <linkedin_url>")
    click.echo("To skip: cli skip-match --prospect-id <id>")


@cli.command(name="accept-match")
@click.option("--prospect-id", type=int, required=True)
@click.option("--url", required=True, help="Confirmed LinkedIn company URL")
def accept_match(prospect_id, url):
    """Manually accept a company match - moves prospect from needs_review to pending discovery (people-tab only)."""
    db.init_db()
    with db.transaction() as conn:
        cur = conn.execute(
            """UPDATE prospects SET
                discovery_status='pending',
                discovery_attempts=0,
                linkedin_company_url=?,
                last_discovery_error='manually_confirmed_company'
            WHERE id=? AND discovery_status='needs_review'""",
            (url, prospect_id),
        )
        click.echo(f"Updated {cur.rowcount} row(s). Re-run discover to find decision-maker.")


@cli.command(name="skip-match")
@click.option("--prospect-id", type=int, required=True)
def skip_match(prospect_id):
    """Mark a needs_review prospect as not_found (no LinkedIn match)."""
    db.init_db()
    with db.transaction() as conn:
        cur = conn.execute(
            """UPDATE prospects SET
                discovery_status='not_found',
                last_discovery_error='manually_skipped'
            WHERE id=? AND discovery_status='needs_review'""",
            (prospect_id,),
        )
        click.echo(f"Updated {cur.rowcount} row(s).")


@cli.command()
def dashboard():
    """Start the Flask dashboard on http://localhost:5151"""
    try:
        from . import dashboard as dash
    except ImportError:
        click.echo("⚠️  Flask not installed. Run: pip install flask")
        sys.exit(1)
    dash.run()


# ---------------------------------------------------------------------------
# DM commands
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--name", default="", help="Person's name (used to find thread in /messaging/)")
@click.option("--profile-url", default="", help="LinkedIn profile URL (preferred over --name)")
@click.option("--message", default="", help="Message to send. If omitted, Claude generates one.")
@click.option("--company", default="", help="Company name (context for generation)")
@click.option("--title", default="", help="Person's title (context for generation)")
@click.option("--stage", default="m1",
              type=click.Choice(["m1", "m2", "m3", "m4", "m5", "followup"]),
              help="Sequence stage - controls generation tone and rules")
@click.option("--context", default="", help="Extra context from Prakash (e.g. 'they replied positively')")
@click.option("--conversation", default="", help="Prior message thread text (for follow-ups)")
@click.option("--generate-only", is_flag=True, default=False,
              help="Generate the message and save as draft but do NOT send")
@click.option("--skip-approval", is_flag=True, default=False,
              help="Send without the interactive approval prompt (use carefully)")
def dm(name, profile_url, message, company, title, stage, context, conversation, generate_only, skip_approval):
    """
    Generate and send a contextual LinkedIn DM.

    Two modes:

    1. Pass --message to send a specific text (skip generation):
       cli dm --name "Dan Connelly" --message "Dan - link's there whenever suits..."

    2. Let Claude generate it (using linkedin-gtm-director skill):
       cli dm --profile-url URL --company "Signs Express" --stage followup --context "agreed to demo, calendar sent"

    Always shows the message for approval before sending unless --skip-approval is set.
    """
    db.init_db()

    if not name and not profile_url:
        click.echo("Error: provide --name or --profile-url")
        sys.exit(1)

    # Derive name from profile URL if only URL given
    person_name = name
    if not person_name and profile_url:
        slug = profile_url.rstrip("/").split("/")[-1]
        person_name = slug.replace("-", " ").title()

    # ----------------------------------------------------------------
    # Step 1: Get or generate the message
    # ----------------------------------------------------------------
    if message:
        final_message = message
        click.echo(f"\nMessage provided directly (no generation needed)")
    else:
        click.echo(f"\nGenerating message for {person_name} (stage={stage})...")
        from .dm_generator import generate_dm
        final_message = generate_dm(
            person_name=person_name,
            company=company,
            title=title,
            profile_snapshot="",
            conversation_history=conversation,
            sequence_stage=stage,
            extra_context=context,
        )
        if not final_message:
            click.secho("Generation failed. Check that `claude` CLI is on PATH and authenticated.", fg="red")
            sys.exit(1)

    # ----------------------------------------------------------------
    # Step 2: Save draft to DB
    # ----------------------------------------------------------------
    dm_id = db.create_dm(
        linkedin_person_name=person_name,
        generated_message=final_message,
        linkedin_person_url=profile_url,
        company=company,
        title=title,
        conversation_history=conversation,
        extra_context=context,
        sequence_stage=stage,
    )
    click.echo(f"\nDraft saved (id={dm_id})")

    # ----------------------------------------------------------------
    # Step 3: Show message for approval
    # ----------------------------------------------------------------
    click.echo(f"\n{'='*60}")
    click.echo(f"TO:      {person_name}" + (f" at {company}" if company else ""))
    if profile_url:
        click.echo(f"PROFILE: {profile_url}")
    click.echo(f"STAGE:   {stage}")
    click.echo(f"\nMESSAGE:\n")
    click.echo(final_message)
    click.echo(f"\n{'='*60}")

    if generate_only:
        db.approve_dm(dm_id, note="generate_only - not sent")
        click.echo("Draft saved. Run `cli dm-send --id {dm_id}` to send later.")
        return

    # ----------------------------------------------------------------
    # Step 4: Approval gate
    # ----------------------------------------------------------------
    if not skip_approval:
        choice = click.prompt(
            "\nSend this message? [y=send / e=edit / n=cancel]",
            default="y",
        ).strip().lower()

        if choice == "e":
            edited = click.edit(final_message)
            if edited and edited.strip():
                final_message = edited.strip()
                click.echo("\nEdited message:")
                click.echo(final_message)
                confirm = click.confirm("Send edited version?", default=True)
                if not confirm:
                    db.reject_dm(dm_id, note="user cancelled after edit")
                    click.echo("Cancelled.")
                    return
            else:
                click.echo("No changes made.")

        elif choice != "y":
            db.reject_dm(dm_id, note="user cancelled at approval prompt")
            click.echo("Cancelled. Draft saved as rejected.")
            return

    db.approve_dm(dm_id)

    # ----------------------------------------------------------------
    # Step 5: Send
    # ----------------------------------------------------------------
    from .browser import Browser
    from .dm_sender import send_dm_from_profile, send_dm_via_messaging

    click.echo("\nOpening Chrome...")
    with Browser() as br:
        if not br.is_logged_in():
            click.secho("Not logged into LinkedIn. Run: cli login", fg="red")
            sys.exit(1)

        if profile_url:
            result = send_dm_from_profile(br, profile_url, final_message)
        else:
            result = send_dm_via_messaging(br, person_name, final_message)

    if result.status == "sent":
        db.update_dm_sent(dm_id, screenshot_path=result.screenshot_path)
        click.secho(f"\nSent to {person_name}!", fg="green", bold=True)
        if result.screenshot_path:
            click.echo(f"Screenshot: {result.screenshot_path}")
    elif result.status == "blocked":
        db.update_dm_error(dm_id, result.error)
        click.secho(f"\nBLOCKED by LinkedIn: {result.error}", fg="red", bold=True)
        click.echo("Check your LinkedIn account before retrying.")
        sys.exit(2)
    else:
        db.update_dm_error(dm_id, result.error, screenshot_path=result.screenshot_path)
        click.secho(f"\nFailed ({result.status}): {result.error}", fg="red")
        if result.screenshot_path:
            click.echo(f"Screenshot: {result.screenshot_path}")
        sys.exit(1)


@cli.command(name="dm-status")
@click.option("--limit", default=10, help="Number of recent DMs to show")
def dm_status(limit):
    """Show recent DM history."""
    db.init_db()
    rows = db.recent_dms(limit)
    if not rows:
        click.echo("No DMs yet.")
        return

    click.echo(f"\n{'='*70}")
    click.echo(f"Recent DMs (last {limit})")
    click.echo(f"{'='*70}\n")
    for r in rows:
        status_color = {"sent": "green", "error": "red", "draft": "yellow", "approved": "cyan"}.get(r["status"], "white")
        click.echo(
            click.style(f"[{r['id']}] {r['status'].upper():10s}", fg=status_color) +
            f" {r['linkedin_person_name']:25s}" +
            (f" at {r['company']}" if r["company"] else "") +
            f"  stage={r['sequence_stage']}"
        )
        click.echo(f"     {(r['generated_message'] or '')[:90]}...")
        if r["sent_at"]:
            click.echo(f"     Sent: {r['sent_at']}")
        click.echo()


@cli.command(name="dm-batch")
@click.option("--connections-json", default="/tmp/linkedin_print_connections.json",
              type=click.Path(exists=True),
              help="JSON output from find_connections command")
@click.option("--limit", default=10, help="Max DMs to generate and send today")
@click.option("--stage", default="m1",
              type=click.Choice(["m1", "m2", "m3", "m4", "m5", "followup"]),
              help="Sequence stage for all messages")
@click.option("--exclude", default="", help="Comma-separated names to skip (e.g. 'Damien Behan,Warren Fox')")
def dm_batch(connections_json, limit, stage, exclude):
    """
    Generate contextual DMs for print/promo connections found by find_connections.

    Workflow:
      1. Reads the JSON produced by: python -m linkedin_automation.find_connections
      2. Filters out excluded names
      3. Generates a personalised message per person using linkedin-gtm-director
      4. Shows ALL drafts in one review pass
      5. You pick which ones to send (IDs or 'all')
      6. Opens Chrome once and sends selected messages back-to-back
    """
    import json as _json
    db.init_db()

    # Load connections
    with open(connections_json) as f:
        connections = _json.load(f)

    # Build exclusion set (lowercase)
    excluded = {n.strip().lower() for n in exclude.split(",") if n.strip()}
    # Always skip known design partners / hot leads already in TaggIQ pipeline
    always_skip = {
        "damien behan", "paul rivers", "declan power",
        "sharon bates", "linda prudden",
        "cian gleeson", "shah jamal", "mark basquille",
        "walter miska", "andrew titus", "jon lambert",
    }
    excluded |= always_skip

    # Filter
    candidates = [
        c for c in connections
        if c.get("name", "").lower() not in excluded
    ][:limit]

    if not candidates:
        click.echo("No candidates after filtering. Run find_connections first.")
        return

    click.echo(f"\nGenerating messages for {len(candidates)} connections (stage={stage})...")
    click.echo("This takes ~10 seconds per person.\n")

    from .dm_generator import generate_dm

    drafts = []
    for i, c in enumerate(candidates, 1):
        name = c.get("name", "Unknown")
        company = c.get("company", "")
        title = c.get("title", "")
        snapshot = c.get("profile_snapshot", "")[:2000]
        about = c.get("about_snippet", "")
        recent_post = c.get("recent_post_snippet", "")

        profile_context = f"Title: {title}\nCompany: {company}\nAbout: {about}\nRecent post: {recent_post}"

        click.echo(f"  [{i}/{len(candidates)}] Generating for {name} ({title} at {company})...")

        msg = generate_dm(
            person_name=name,
            company=company,
            title=title,
            profile_snapshot=snapshot,
            sequence_stage=stage,
            extra_context=f"1st-degree LinkedIn connection in print/promo industry.",
        )

        if not msg:
            click.secho(f"    Generation failed for {name} - skipping", fg="yellow")
            continue

        dm_id = db.create_dm(
            linkedin_person_name=name,
            generated_message=msg,
            linkedin_person_url=c.get("url", ""),
            company=company,
            title=title,
            profile_context=profile_context,
            sequence_stage=stage,
        )
        drafts.append({"id": dm_id, "name": name, "company": company, "url": c.get("url", ""), "message": msg})

    if not drafts:
        click.echo("No messages generated.")
        return

    # Show all drafts for one review pass
    click.echo(f"\n{'='*65}")
    click.echo(f"REVIEW - {len(drafts)} messages generated")
    click.echo(f"{'='*65}\n")
    for d in drafts:
        click.echo(click.style(f"[{d['id']}] {d['name']}", bold=True) +
                   (f" - {d['company']}" if d["company"] else ""))
        click.echo(f"{d['message']}")
        click.echo()

    click.echo(f"{'='*65}")
    raw = click.prompt(
        "\nWhich to send? Enter IDs comma-separated, 'all', or 'none'",
        default="all",
    ).strip().lower()

    if raw == "none":
        click.echo("Nothing sent. All drafts saved for later.")
        return

    if raw == "all":
        to_send = drafts
    else:
        try:
            ids = {int(x.strip()) for x in raw.split(",")}
            to_send = [d for d in drafts if d["id"] in ids]
        except ValueError:
            click.echo("Invalid input. Nothing sent.")
            return

    if not to_send:
        click.echo("No valid IDs selected.")
        return

    # Approve selected
    for d in to_send:
        db.approve_dm(d["id"])

    # Send in one Chrome session
    from .browser import Browser
    from .dm_sender import send_dm_from_profile, send_dm_via_messaging

    click.echo(f"\nOpening Chrome to send {len(to_send)} messages...")
    sent = 0
    failed = 0

    with Browser() as br:
        if not br.is_logged_in():
            click.secho("Not logged into LinkedIn. Run: cli login", fg="red")
            sys.exit(1)

        for d in to_send:
            click.echo(f"  Sending to {d['name']}...")
            if d["url"]:
                result = send_dm_from_profile(br, d["url"], d["message"])
            else:
                result = send_dm_via_messaging(br, d["name"], d["message"])

            if result.status == "sent":
                db.update_dm_sent(d["id"], screenshot_path=result.screenshot_path)
                click.secho(f"  Sent to {d['name']}", fg="green")
                sent += 1
            elif result.status == "blocked":
                db.update_dm_error(d["id"], result.error)
                click.secho(f"  BLOCKED by LinkedIn. Stopping.", fg="red", bold=True)
                break
            else:
                db.update_dm_error(d["id"], result.error, screenshot_path=result.screenshot_path)
                click.secho(f"  Failed ({d['name']}): {result.error}", fg="red")
                failed += 1

            # Pause between messages - look human
            if d != to_send[-1]:
                import random, time
                delay = random.uniform(45, 90)
                click.echo(f"  Pausing {delay:.0f}s...")
                time.sleep(delay)

    click.echo(f"\nDone. Sent: {sent}  Failed: {failed}")


def main():
    cli()


if __name__ == "__main__":
    main()
