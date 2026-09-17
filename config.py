"""Central knobs. Edit these to tune scoring without touching the engine."""
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "recruiting.db"
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
# Jobs located outside the US are capped here (lands them in REVIEW at best).
NON_US_CAP = 6.0

# Overall score thresholds for the dashboard buckets.
HIGH_PRIORITY_MIN = 8.0
REVIEW_MIN = 5.5

# Polite fetching.
REQUEST_TIMEOUT = 20
DELAY_BETWEEN_SOURCES = 0.5
USER_AGENT = "recruiting-copilot/0.1 (personal job search tool)"
