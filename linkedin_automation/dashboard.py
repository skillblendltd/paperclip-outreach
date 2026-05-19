"""
Read-only Flask dashboard for the LinkedIn automation pipeline.

Shows:
- Per-country progress (discovery + connection)
- Daily / weekly invite counts vs caps
- Recent events stream with screenshots
- List of pending / blocked / errored prospects

Modifies NOTHING. View-only.
"""

from __future__ import annotations

from flask import Flask, jsonify, render_template, send_file
from pathlib import Path

from . import config, db


app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """All stats for the dashboard."""
    conn = db.get_connection()
    try:
        cur = conn.execute("SELECT DISTINCT country_code FROM prospects ORDER BY country_code")
        countries = [r["country_code"] for r in cur.fetchall()]
    finally:
        conn.close()

    country_data = []
    for cc in countries:
        s = db.country_stats(cc)
        country_data.append({
            "country": cc,
            "total": s.total,
            "discovery_done": s.discovery_done,
            "discovery_pending": s.discovery_pending,
            "discovery_not_found": s.discovery_not_found,
            "discovery_needs_review": s.discovery_needs_review,
            "connection_sent": s.connection_sent,
            "connection_pending": s.connection_pending,
            "connection_already_connected": s.connection_already_connected,
            "connection_error": s.connection_error,
        })

    return jsonify({
        "countries": country_data,
        "daily_sent": db.daily_invite_count(),
        "weekly_sent": db.weekly_invite_count(),
        "weekly_cap": config.CONNECTION_WEEKLY_CAP,
        "daily_cap_default": config.CONNECTION_DAILY_CAP_DEFAULT,
    })


@app.route("/api/events")
def api_events():
    rows = db.recent_events(limit=100)
    return jsonify([
        {
            "id": r["id"],
            "type": r["event_type"],
            "prospect": r["business_name"] if "business_name" in r.keys() else None,
            "country": r["country_code"] if "country_code" in r.keys() else None,
            "detail": r["detail"],
            "screenshot": r["screenshot_path"],
            "created_at": r["created_at"],
        }
        for r in rows
    ])


@app.route("/screenshot/<path:relpath>")
def screenshot(relpath):
    path = config.SCREENSHOTS_DIR / Path(relpath).name
    if path.exists():
        return send_file(str(path))
    return "Not found", 404


def run():
    print(f"🚀 Dashboard at http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False)
