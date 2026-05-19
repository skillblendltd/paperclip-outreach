# LinkedIn Connection Automation - Architecture & Plan

**Author:** CTO Architect
**Date:** 2026-05-18
**Status:** DESIGN
**Scope:** Automate LinkedIn connection requests for 1,007 IE + 4,000+ UK print/promo businesses (~5,000 total)

---

## 1. Problem Statement

We have ~5,000 print and promo businesses across Ireland and the UK in CSV form. We need to send each one a LinkedIn connection request - no note - in a way that:

- Looks natural enough that LinkedIn does not flag the account
- Is resumable if the script crashes or is paused
- Tracks success/failure per prospect
- Can be repeated for new countries/segments without re-architecture

This is NOT a one-off script. It is the first iteration of what becomes the **LinkedIn channel** of the autonomous outbound pipeline (TaggIQ, FP, Kritno, etc.).

---

## 2. Goals & Non-Goals

### Goals
- Send ~5,000 connection requests over 4-6 months at human-safe pace
- Zero account suspensions or warnings from LinkedIn
- Full audit trail: who was contacted, when, outcome
- Resumable across crashes, daily sessions, machine reboots
- Reusable for future country/segment lists (UK, US, etc.)

### Non-Goals (for v1)
- Sending messages after connecting (different problem, future sprint)
- Multi-account orchestration (single account for now)
- Headless / fully unattended (we explicitly want a real Chrome window)
- Connection notes (we send WITHOUT notes - acceptance rate is higher)
- Sales Navigator (use free LinkedIn first, upgrade only if needed)

---

## 3. Key Architectural Decisions

| Decision | Choice | Why |
|---|---|---|
| Browser library | Selenium + `undetected-chromedriver` | Playwright has known fingerprints LinkedIn detects. UC actively patches Chrome to evade detection. |
| Headless? | NO - real Chrome window | Headless mode is the #1 detection signal. Visible browser = looks human. |
| Login | Manual one-time, persistent profile | Storing LinkedIn passwords + auto-login = instant flag. Persistent Chrome profile keeps session alive. |
| State store | SQLite | Single-user, single-machine. PostgreSQL is overkill. Easy backups. |
| Pace | 25-40 connections/day MAX | LinkedIn enforces ~100 invites/week for free accounts. Safe pace = ~150/week, below limit. |
| Target | Decision-makers on company page | Cannot connect to company pages (only follow). Find owner/CEO/founder via company "People" tab. |
| Phases | Discovery → Connection (separated) | Different risk profiles. Discovery is read-only. Allows running discovery faster, connection slower. |
| Resume strategy | Status-based DB queries | Every prospect has a status. Runner always queries `WHERE status='pending' AND attempts < 3`. |
| Failure handling | Circuit breaker on 429/403 | If LinkedIn blocks, STOP immediately, alert user, do not retry until manual review. |

---

## 4. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Operator (Prakash)                        │
│   - Imports CSVs    - Runs CLI    - Reviews dashboard       │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │   CLI / Dashboard       │
              │ (linkedin_automation)   │
              └────────────┬────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌──────▼──────┐     ┌────▼─────┐
   │Importer │      │  Runner     │     │ Dashboard│
   │(CSV→DB) │      │ (Orchestrator│     │ (Flask)  │
   └────┬────┘      └──┬──────┬───┘     └────┬─────┘
        │              │      │              │
        │     ┌────────┘      └─────────┐    │
        │     │                         │    │
        │  ┌──▼──────┐           ┌──────▼─┐  │
        │  │Discovery│           │Connector│ │
        │  │ Module  │           │ Module  │ │
        │  └────┬────┘           └────┬────┘ │
        │       │                     │      │
        │       └──────┬──────────────┘      │
        │              │                     │
        │      ┌───────▼────────┐            │
        │      │ Browser Layer  │            │
        │      │ (Selenium+UC)  │            │
        │      └───────┬────────┘            │
        │              │                     │
        │      ┌───────▼────────┐            │
        │      │Human Simulator │            │
        │      │(delays,scroll, │            │
        │      │ mouse, typing) │            │
        │      └────────────────┘            │
        │                                    │
        └──────────────┬─────────────────────┘
                       │
              ┌────────▼────────┐
              │  SQLite DB      │
              │ - prospects     │
              │ - events        │
              │ - sessions      │
              └─────────────────┘
```

### Module Boundaries

| Module | Responsibility | Does NOT |
|---|---|---|
| `db.py` | Schema, CRUD, transactions | Talk to LinkedIn, parse HTML |
| `browser.py` | Chrome lifecycle, stealth config, profile mgmt | Know about LinkedIn URLs or business logic |
| `human.py` | Random delays, mouse, scroll, typing | Make decisions about what to do |
| `search.py` | Find LinkedIn company page + decision-maker | Click connect, modify state |
| `connect.py` | Click connect, handle modals, confirm | Find profiles, store state directly |
| `runner.py` | Sequence operations, enforce pacing, retry | Implement individual actions |
| `cli.py` | Operator commands | Long-running automation logic |
| `dashboard.py` | Read-only status views | Modify state, drive automation |

**Rule:** Anything calling LinkedIn goes through `browser.py`. Anything making decisions about pacing goes through `runner.py`. No module imports its own peers' internals - only the modules below it.

---

## 5. Data Model

```sql
-- Master list of prospects (imported from CSV, enriched over time)
CREATE TABLE prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,            -- Hash of business_name+email+city (dedup key)

    -- From CSV
    business_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    website TEXT,
    city TEXT,
    region TEXT,                        -- "Ireland", "UK" etc.
    country_code TEXT,                  -- "IE", "GB"
    segment TEXT,                       -- "promo_distributor", "sign_shop" etc.

    -- Discovered (Phase 1)
    linkedin_company_url TEXT,          -- linkedin.com/company/xxx
    linkedin_company_id TEXT,           -- numeric ID if available
    linkedin_person_url TEXT,           -- linkedin.com/in/xxx (decision-maker)
    linkedin_person_name TEXT,
    linkedin_person_title TEXT,

    -- Status tracking
    discovery_status TEXT DEFAULT 'pending',  -- pending|done|not_found|error|skipped
    connection_status TEXT DEFAULT 'pending', -- pending|sent|accepted|already_connected|not_found|blocked|error

    -- Attempts
    discovery_attempts INTEGER DEFAULT 0,
    connection_attempts INTEGER DEFAULT 0,
    last_discovery_error TEXT,
    last_connection_error TEXT,

    -- Timestamps
    discovered_at DATETIME,
    connected_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_discovery_status ON prospects(discovery_status, country_code);
CREATE INDEX idx_connection_status ON prospects(connection_status, country_code);

-- Audit trail of every action taken
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER,
    event_type TEXT NOT NULL,           -- discovery_started|discovery_done|connect_clicked|connect_confirmed|blocked|error
    detail TEXT,                        -- JSON payload
    screenshot_path TEXT,               -- For debugging
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(prospect_id) REFERENCES prospects(id)
);

CREATE INDEX idx_events_prospect ON events(prospect_id, created_at);

-- Session tracking (each run = a session)
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_type TEXT,                  -- discovery|connection
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    prospects_processed INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    blocked BOOLEAN DEFAULT 0,          -- Did LinkedIn block us?
    notes TEXT
);
```

---

## 6. Workflow

### Phase 0 — Setup (one-time, ~30 mins)

```bash
# Install dependencies
pip install undetected-chromedriver selenium beautifulsoup4 flask click

# Initialize DB
python -m linkedin_automation.cli init

# Import IE prospects
python -m linkedin_automation.cli import \
    --csv google-maps-scraper/output/ireland_print_promo.csv \
    --country IE

# One-time browser setup + login
python -m linkedin_automation.cli login
# → Opens real Chrome window
# → You log in manually
# → Browser saves session in ~/.linkedin_automation_profile/
# → You close browser
# → All future runs use this profile
```

### Phase 1 — Discovery (parallel-safe, ~2 weeks for 1,007 IE)

```bash
# Runs in foreground, processes batch of N prospects per session
python -m linkedin_automation.cli discover \
    --country IE \
    --batch-size 30
# → Searches LinkedIn for each company
# → Finds owner/CEO/founder profile
# → Stores linkedin_person_url in DB
# → Sleeps 30-90s between searches
# → Stops at batch-size or end of pending list
# → Safe to run multiple times per day
```

Why discovery first?
- Read-only operations have lower block risk
- Can run 100-200 searches/day (vs 25-40 connections/day)
- Validates data quality BEFORE we burn connection-request budget
- Bad CSV rows surface here (no LinkedIn presence = filtered out)

### Phase 2 — Connection (serial, 25-40/day)

```bash
# Daily run during work hours
python -m linkedin_automation.cli connect \
    --country IE \
    --daily-cap 30
# → Picks prospects with discovery_status='done' and connection_status='pending'
# → Visits profile, clicks Connect, sends without note
# → Sleeps 60-180s between requests
# → Stops at daily_cap or end of pending list
# → ALERTS if blocked (429/403) and exits
```

### Phase 3 — Monitor (always available)

```bash
# Start dashboard
python -m linkedin_automation.cli dashboard
# → Opens http://localhost:5151
# → Shows: total/discovered/connected/blocked per country
# → Shows: recent events, errors with screenshots
# → Shows: daily rate, weekly rate (vs LinkedIn caps)
```

---

## 7. Risk & Failure Modes

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LinkedIn account suspended | Medium | High - lose primary outreach channel | Stay under 100 invites/week. Stop on first 429. Use real browser. |
| LinkedIn changes DOM selectors | High (quarterly) | Medium - script breaks | Use stable selectors (`aria-label`, `data-testid`). Log full HTML on failure. |
| IP flagged by LinkedIn | Low | High - all activity blocked | Run from home residential IP. NOT VPN. NOT datacenter. |
| Wrong person targeted (intern instead of owner) | Medium | Low - low acceptance rate | Prioritize titles: Owner > Founder > CEO > MD > Director > Manager. |
| CSV has bad data | High | Low - filtered in discovery | Discovery phase surfaces "not_found" rows. Manual review. |
| Crash mid-batch | Medium | Low - lose 1-2 prospects worst case | Status committed after EVERY action. Resume picks up automatically. |
| Connection sent but UI says "already connected" | Medium | Low | Idempotent: mark as `already_connected`, not retry. |
| Already-pending invitation | Medium | Low | Detect "Pending" state, mark as `sent` without re-clicking. |

### Hard Stop Conditions (Circuit Breaker)

The runner exits immediately if any of these occur:

1. LinkedIn returns HTTP 429 (rate limited)
2. LinkedIn redirects to `/checkpoint/challenge` (verification required)
3. LinkedIn shows "You're out of invitations" banner
4. 3+ consecutive errors of any type
5. Profile fails to load (network issue or block)

When a hard stop occurs:
- Set `sessions.blocked = 1`
- Email/notify operator
- Do NOT retry automatically
- Operator must manually verify account health on LinkedIn, then resume

---

## 8. Implementation Plan

| # | Task | Phase | Size | Status |
|---|------|-------|------|--------|
| 1 | Architecture doc (this file) | 1 | Small | In Progress |
| 2 | Create `linkedin_automation/` module skeleton | 1 | Small | Pending |
| 3 | Database schema + `db.py` | 1 | Medium | Pending |
| 4 | CSV importer (CSV → prospects table) | 1 | Small | Pending |
| 5 | Stealth browser (`browser.py`) | 1 | Medium | Pending |
| 6 | Human simulator (`human.py`) | 1 | Small | Pending |
| 7 | Login command (manual one-time) | 1 | Small | Pending |
| 8 | LinkedIn search module (`search.py`) | 2 | Large | Pending |
| 9 | Decision-maker selection logic | 2 | Medium | Pending |
| 10 | Connection sender (`connect.py`) | 3 | Large | Pending |
| 11 | Already-connected/pending detection | 3 | Medium | Pending |
| 12 | Runner + rate limiter | 4 | Medium | Pending |
| 13 | Circuit breaker on 429/403 | 4 | Small | Pending |
| 14 | CLI (Click-based) | 5 | Medium | Pending |
| 15 | Flask dashboard | 5 | Medium | Pending |
| 16 | Smoke test on 10 IE prospects | 6 | Small | Pending |
| 17 | Full IE discovery run | 6 | Large | Pending |
| 18 | Full IE connection run | 6 | Large | Pending |
| 19 | UK import + rinse-and-repeat | 7 | Medium | Pending |

---

## 9. File/Folder Structure

```
linkedin_automation/
├── __init__.py
├── cli.py                 # Operator commands (Click)
├── db.py                  # SQLite schema + queries
├── importer.py            # CSV → prospects
├── browser.py             # Selenium + undetected-chromedriver wrapper
├── human.py               # Delays, mouse, scroll, typing
├── search.py              # Find LinkedIn company + decision-maker
├── connect.py             # Click Connect, handle modals
├── runner.py              # Orchestrator with rate limiting
├── dashboard.py           # Flask app (port 5151)
├── config.py              # All tunable constants
├── templates/             # Dashboard HTML
│   └── index.html
├── data/                  # SQLite DB lives here
│   └── linkedin.db
├── logs/                  # Per-session logs
└── screenshots/           # Failure screenshots
```

Database and Chrome profile are stored OUTSIDE the repo:
- DB: `~/.linkedin_automation/linkedin.db`
- Chrome profile: `~/.linkedin_automation/chrome_profile/`

This means: deleting the repo does not lose state. Committing the repo does not commit cookies.

---

## 10. Implementation Contract

### What MUST be done

- All LinkedIn navigation via `browser.py` - no direct `driver.get()` elsewhere
- All status changes via `db.py` transactions - no raw SQL elsewhere
- Every action logged to `events` table BEFORE the action runs (we want to see partial failures)
- Every error captured with a screenshot in `screenshots/<timestamp>_<prospect_id>.png`
- Every selector uses stable attributes (`aria-label`, `data-testid`) - never class names

### What MUST NOT be done

- No hardcoded sleeps - all delays go through `human.py` (which randomizes them)
- No credentials in code, env vars, or DB - LinkedIn login is manual only
- No multi-threaded LinkedIn requests - pattern detection
- No parallel sessions - one Chrome instance at a time
- No retry without operator approval after a 429
- No "warming up" by liking/commenting - that's a different feature, different sprint

---

## 11. Definition of Done

**Phase 1 (Foundation):**
- [ ] Repo runs `python -m linkedin_automation.cli init` cleanly on fresh machine
- [ ] Can import 1,007 IE prospects with zero duplicates
- [ ] Can launch Chrome, log in manually, close, relaunch with session preserved

**Phase 2 (Discovery):**
- [ ] 10 hand-picked IE businesses discovered correctly (right company + senior person)
- [ ] Failures logged with screenshots
- [ ] Resume from row 5 works after manual crash

**Phase 3 (Connection):**
- [ ] 5 hand-picked discovered prospects connected to
- [ ] "Already connected" prospects marked correctly, not duplicated
- [ ] Circuit breaker triggers on simulated 429

**Phase 4 (Production):**
- [ ] Full IE run completes (target: 6 weeks)
- [ ] Dashboard shows accurate counts
- [ ] No LinkedIn warnings received
- [ ] UK rerun is one command, no code changes

---

## 12. Open Questions

1. **Should we connect to multiple decision-makers per company?** For now: NO. One per company. Lower acceptance rate from spam pattern.
2. **Should we use Sales Navigator?** For now: NO. Free tier first. Upgrade only if invite limits become binding.
3. **Should we send notes?** Per spec: NO. Without-note connection has higher acceptance rate (research shows ~15-30% higher).
4. **Multi-account in future?** Out of scope for v1. Architecture supports it (sessions table has session_id; can add account_id later).

---

## 13. Reference Links

- LinkedIn's automation policy: https://www.linkedin.com/help/linkedin/answer/56347
- `undetected-chromedriver` docs: https://github.com/ultrafunkamsterdam/undetected-chromedriver
- LinkedIn invite limits explained: ~100/week for free, ~200/week with Premium
