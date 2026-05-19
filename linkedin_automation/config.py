"""
All tunable constants for the LinkedIn automation system.

Edit here, not in code. Anything that might need to change between
countries, segments, or LinkedIn policy updates lives here.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Data lives outside the repo so cookies/cache don't get committed
HOME_DIR = Path(os.environ.get("LINKEDIN_AUTOMATION_HOME", Path.home() / ".linkedin_automation"))
DB_PATH = HOME_DIR / "linkedin.db"
CHROME_PROFILE_DIR = HOME_DIR / "chrome_profile"

# Logs and screenshots in repo for debugging access
REPO_DIR = Path(__file__).parent
LOGS_DIR = REPO_DIR / "logs"
SCREENSHOTS_DIR = REPO_DIR / "screenshots"


# ---------------------------------------------------------------------------
# Pacing (the most important knobs - tune carefully)
# ---------------------------------------------------------------------------

# Discovery phase (read-only, lower risk)
DISCOVERY_DELAY_MIN_SEC = 25
DISCOVERY_DELAY_MAX_SEC = 70
DISCOVERY_BATCH_SIZE_DEFAULT = 30
DISCOVERY_DAILY_CAP = 150  # Read-only, can be aggressive

# Connection phase (active, higher risk)
CONNECTION_DELAY_MIN_SEC = 60
CONNECTION_DELAY_MAX_SEC = 180
CONNECTION_DAILY_CAP_DEFAULT = 30
CONNECTION_WEEKLY_CAP = 150  # LinkedIn enforces ~100/week, we stay under

# Mid-session pauses (every N actions, longer break)
SESSION_PAUSE_AFTER_N_ACTIONS = 8
SESSION_PAUSE_MIN_SEC = 300   # 5 min
SESSION_PAUSE_MAX_SEC = 900   # 15 min

# Retries
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SEC = 60


# ---------------------------------------------------------------------------
# Human simulation
# ---------------------------------------------------------------------------

# Mouse movement before clicking
MOUSE_MOVE_STEPS_MIN = 3
MOUSE_MOVE_STEPS_MAX = 8

# Scroll behavior
SCROLL_PROBABILITY = 0.6        # 60% chance to scroll on a page
SCROLL_DISTANCE_MIN = 200
SCROLL_DISTANCE_MAX = 800

# Typing cadence (per character)
TYPING_DELAY_MIN_SEC = 0.05
TYPING_DELAY_MAX_SEC = 0.18

# Page-load wait
PAGE_LOAD_PAUSE_MIN_SEC = 2.0
PAGE_LOAD_PAUSE_MAX_SEC = 5.0


# ---------------------------------------------------------------------------
# Circuit breaker - hard stop conditions
# ---------------------------------------------------------------------------

# If we hit these, the runner exits and requires manual intervention
HARD_STOP_PATTERNS = [
    "/checkpoint/challenge",
    "Unusual activity",
    "We restricted your account",
    "out of invitations",
    "Reached the weekly invitation limit",
    "We've temporarily restricted",
]

# After N consecutive errors of any kind, stop
CONSECUTIVE_ERROR_LIMIT = 3


# ---------------------------------------------------------------------------
# Decision-maker selection (in priority order)
# ---------------------------------------------------------------------------

DECISION_MAKER_TITLE_PRIORITY = [
    "owner",
    "founder",
    "co-founder",
    "co founder",
    "ceo",
    "managing director",
    "md",
    "president",
    "general manager",
    "director",
    "head of",
    "vp",
    "vice president",
    "manager",
]

# Skip these titles - they are not decision-makers for a B2B sales pitch
SKIP_TITLE_PATTERNS = [
    "intern",
    "assistant",
    "trainee",
    "graduate",
    "student",
    "apprentice",
]


# ---------------------------------------------------------------------------
# Company matching (LinkedIn search → CSV row)
# ---------------------------------------------------------------------------

# Max search-result candidates to score
MATCH_CANDIDATE_LIMIT = 10

# Min score to AUTO-accept a match (without website verification)
MATCH_MIN_AUTO_SCORE = 12

# Min score to attempt verification (load /about/, check website)
MATCH_MIN_VERIFY_SCORE = 3

# Score floor: anything below this is treated as "not_found"
MATCH_HARD_FLOOR = 3

# Score awarded when website domain matches CSV domain - dominant signal
MATCH_DOMAIN_BONUS = 20

# LinkedIn geo URNs - pre-filter search to country.
# These are LinkedIn's internal IDs and rarely change.
COUNTRY_GEO_URN = {
    "IE": "104738515",   # Ireland
    "GB": "101165590",   # United Kingdom
    "US": "103644278",   # United States
    "CA": "101174742",   # Canada
    "AU": "101452733",   # Australia
}

# Words to drop when computing token-overlap score (uninformative)
COMPANY_NAME_STOPWORDS = {
    "the", "a", "an", "and", "of", "for",
    "ltd", "limited", "llc", "inc", "incorporated", "corp", "corporation",
    "company", "co", "plc", "gmbh", "sa", "bv", "pty",
    "group", "holdings", "international", "global",
}


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

CHROME_HEADLESS = False  # NEVER set to True - headless = instant detection
CHROME_WINDOW_SIZE = (1366, 900)  # Common laptop resolution
USER_AGENT = None  # Let undetected-chromedriver pick a natural one


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_PORT = 5151
DASHBOARD_HOST = "127.0.0.1"
