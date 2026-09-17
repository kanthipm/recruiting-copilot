# recruiting-copilot

A free, local job opportunity engine. Every day it pulls new postings from 100+ public job
boards, scores each one against `profile.json` with a transparent rule-based scorer, and shows
a ranked shortlist of **new-grad / early-career roles in the US posted in the last 2 days** in a
Streamlit dashboard. You decide what to apply to; Simplify handles the application itself.

```
fetch (Greenhouse / Lever / Ashby)  ->  SQLite  ->  score against profile.json  ->  dashboard / CLI shortlist
```

## Setup (once)

```powershell
git clone https://github.com/kanthipm/recruiting-copilot
cd recruiting-copilot
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Daily use

```powershell
python run.py daily               # fetch new jobs, score them, print the shortlist
python run.py dashboard           # open the Streamlit dashboard (http://localhost:8501)
```

`daily` only scores jobs it hasn't scored yet, so it's fast after the first run. The shortlist
shows jobs posted in the last 2 days (`--days 0` for everything), highest score first.

## Other commands

| Command | What it does |
|---|---|
| `python run.py fetch` | Pull jobs from every source in `sources.json` (dedupes by URL) |
| `python run.py score` | Score unscored jobs. `--rescore` re-scores everything (run after editing `profile.json` or `config.py`) |
| `python run.py shortlist --why` | Print HIGH / REVIEW lists with the reason and URL for each (`--days N` to widen the window) |
| `python run.py explain <job_id>` | Full dimension-by-dimension breakdown for one job |
| `python run.py check-sources` | Verify every board in `sources.json` responds |

## Files you'll edit

- **`profile.json`**: your skills, experiences, target roles, location preferences, keyword lists,
  and the `avoid` lists (titles to drop, seniority words). The scorer reads only this file, so
  reasons stay tied to your real background.
- **`sources.json`**: one line per company board. `board` is the token from the company's job URL
  (`boards.greenhouse.io/<board>`, `jobs.lever.co/<board>`, `jobs.ashbyhq.com/<board>`).
  `quality` (1-5) is your own opinion of the company and is the only "company quality" signal.
- **`config.py`**: dimension weights, HIGH/REVIEW thresholds, the 2-day window (`RECENT_DAYS`),
  and the two hard gates: `REQUIRE_EARLY_CAREER` and `US_ONLY`.

After editing any of these: `python run.py score --rescore`.

## How scoring works

Ten dimensions, each 0-10 with a note citing the evidence found in the posting:

| Dimension | Signal |
|---|---|
| eligibility | Senior title words, "N+ years experience", new-grad phrases, internships, your avoid list |
| career | Title -> role type (`src/scoring/text.py`) -> your `target_roles` interest |
| technical | Overlap between the description and `technical_skills` |
| ai | AI/ML keywords in title and description, AI-industry company |
| product | PM/product-engineer role type, or product-ownership keywords |
| hybrid | The weaker of technical and product, +2 for explicitly hybrid titles (FDE, product engineer) |
| startup | `company_type` / `stage` from `sources.json`, plus early-stage language |
| company_quality | Your 1-5 rating in `sources.json` x 2 |
| location | Preferred / acceptable / remote / non-US (from `location_preferences`) |
| healthcare | Healthcare company or clinical keywords (low weight; a bonus) |

Overall = weighted mean (weights in `config.py`). Hard gates keep the list honest. A job is
capped at 3.5 (SKIP) if any of these hold:

- senior title, or requires more than 2 years of experience
- no early-career signal at all (no new-grad wording and no years stated) when `REQUIRE_EARLY_CAREER` is on
- located outside the US when `US_ONLY` is on
- title doesn't map to any target role (sales, design, hardware, etc.)

HIGH >= 8.0, REVIEW >= 5.5, otherwise SKIP.

The score is rule-based and interpretable on purpose. It is good at ranking, not at
distinguishing an 8.4 from an 8.6. Use the reason text and the breakdown table.

## Adding a source

1. Find the company's job board URL and note the platform + token.
2. Add a line to `sources.json`.
3. `python run.py check-sources` to confirm it responds, then `python run.py daily`.

To support a new platform, subclass `Collector` in `src/collectors/`, return a list of `Job`,
and register it in `src/collectors/__init__.py`.

## Project layout

```
run.py                   CLI entry point
config.py                weights, thresholds, paths
profile.json             your career profile (edit freely)
sources.json             company boards to pull from
src/collectors/          base.py (Job dataclass) + greenhouse.py, lever.py, ashby.py
src/database/db.py       SQLite schema + queries (jobs, companies, applications)
src/scoring/scorer.py    the scoring engine; text.py has role classification + keyword helpers
src/dashboard/app.py     Streamlit UI
data/recruiting.db       created on first run (gitignored)
```

## Ground rules

Only public, unauthenticated job-board APIs are used, with a polite delay between requests.
No LinkedIn, no CAPTCHA/bot-protection bypass, no Simplify automation.

## Roadmap

- V2: LLM-assisted evaluation, resume tailoring, application tracking, email digest
- V3: startup discovery, funding/founder research, founder outreach drafts
- V4: follow-up and interview tracking, analytics
