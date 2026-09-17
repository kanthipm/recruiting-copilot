"""Central knobs. Edit these to tune scoring without touching the engine."""
import os
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get("RECRUITING_DB", ROOT / "data" / "recruiting.db"))
# Slim copy (jobs above REVIEW_MIN, trimmed descriptions) that is committed to git for the hosted dashboard.
SLIM_DB_PATH = ROOT / "data" / "dashboard.db"
SLIM_MAX_DESCRIPTION = 4000
PROFILE_PATH = ROOT / "profile.json"
SOURCES_PATH = ROOT / "sources.json"

# Relative importance of each fit dimension in the overall score.
WEIGHTS = {
    "eligibility": 2.0,
    "career": 2.0,
    "technical": 1.5,
    "ai": 1.5,
    "product": 1.5,
    "hybrid": 1.0,
    "startup": 1.0,
    "company_quality": 1.0,
    "location": 1.0,
    "healthcare": 0.5,
}

# Jobs that fail eligibility (senior titles, 5+ years required) are capped here.
INELIGIBLE_CAP = 3.5
# US only: jobs located outside the US are capped at INELIGIBLE_CAP (SKIP).
# Set to False to merely cap them at NON_US_CAP instead.
US_ONLY = True
NON_US_CAP = 6.0

# Only jobs with an explicit early-career signal (new grad wording, or <= max_years_experience
# stated) are eligible. Everything else is capped at INELIGIBLE_CAP.
REQUIRE_EARLY_CAREER = True

# Default window for the shortlist and dashboard: jobs posted in the last N days.
RECENT_DAYS = 2

# Overall score thresholds for the dashboard buckets.
HIGH_PRIORITY_MIN = 7.5
REVIEW_MIN = 5.5

# Polite fetching.
REQUEST_TIMEOUT = 20
DELAY_BETWEEN_SOURCES = 0.5
USER_AGENT = "recruiting-copilot/0.1 (personal job search tool)"
