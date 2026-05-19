# LinkedIn Connection Automation

Human-paced LinkedIn connection request automation for the Paperklip outreach pipeline.

See `docs/linkedin-automation-plan.md` for full architecture and design rationale.

## Quick start

```bash
# 1. Install dependencies (one-time)
pip install -r linkedin_automation/requirements.txt

# 2. Initialize database
python -m linkedin_automation.cli init

# 3. Import Irish prospects
python -m linkedin_automation.cli import \
    --csv google-maps-scraper/output/ireland_print_promo.csv \
    --country IE

# 4. Log in to LinkedIn (one-time, manual)
python -m linkedin_automation.cli login
#  → Opens Chrome
#  → You log in manually with email/password (and 2FA)
#  → Close Chrome window when done; session is saved

# 5. Phase 1: Discover LinkedIn profiles (run multiple times across days)
python -m linkedin_automation.cli discover --country IE --batch-size 30

# 6. Phase 2: Send connection requests (daily, throttled)
python -m linkedin_automation.cli connect --country IE --daily-cap 30

# 7. Watch progress
python -m linkedin_automation.cli status
python -m linkedin_automation.cli dashboard   # http://localhost:5151
```

## Safe pacing

LinkedIn enforces ~100 invites/week on free accounts. Defaults:

- Discovery: 25-70s between searches, 150/day cap
- Connection: 60-180s between requests, 30/day cap, 150/week cap
- Mid-session breaks: 5-15 min every 8 actions

At these rates, expect:

- **Ireland (1,007 prospects):** ~5-6 weeks
- **UK (4,000+ prospects):** ~5 months

Tune in `linkedin_automation/config.py` if your account history supports more.

## Circuit breaker

If LinkedIn returns a verification challenge, restriction page, or weekly-limit banner,
the runner exits immediately with `BLOCKED` status. Manual review on the LinkedIn
website is required before resuming.

## Resume

Every action commits to the DB before/after running. Crashes don't lose progress.
Re-running `discover` or `connect` picks up exactly where the last session left off.
