"""CLI entry point.

  python run.py daily            fetch + score + print shortlist (the one command you run each day)
  python run.py fetch            pull jobs from every source in sources.json
  python run.py score            score jobs that don't have a score yet (--rescore to redo all)
  python run.py shortlist        print the ranked shortlist from the database
  python run.py dashboard        open the Streamlit dashboard
  python run.py check-sources    verify every source in sources.json responds
  python run.py explain <job_id> print the full score breakdown for one job
  python run.py export           write data/dashboard.db (slim copy for the hosted dashboard)
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

import config
from src.collectors import get_collector
from src.database import db
from src.scoring.scorer import Scorer, load_profile, tier_for


def load_sources() -> list[dict]:
    with open(config.SOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)["sources"]


def title_is_excluded(title: str, profile: dict) -> bool:
    t = title.lower()
    return any(k in t for k in profile["avoid"]["title_keywords"])


# ---------------- commands ----------------

def cmd_fetch(args):
    db.init_db()
    profile = load_profile()
    sources = load_sources()
    total_new = total_seen = total_excluded = 0
    with db.connect() as conn:
        for s in sources:
            db.upsert_company(conn, s)

    for s in sources:
        label = f"{s['collector']}:{s['board']}"
        try:
            jobs = get_collector(s["collector"]).fetch(s)
        except Exception as e:  # keep going; one bad board shouldn't kill the run
            print(f"  [FAIL] {label}: {e}")
            continue
        kept = [j for j in jobs if j.url and not title_is_excluded(j.title, profile)]
        new = db.insert_jobs(kept)
        total_seen += len(jobs)
        total_excluded += len(jobs) - len(kept)
        total_new += new
        print(f"  [ok] {label:<28} {len(jobs):>4} jobs, {len(kept):>4} relevant, {new:>3} new")
        time.sleep(config.DELAY_BETWEEN_SOURCES)

    print(f"\nFetched {total_seen} postings, filtered {total_excluded} by title, {total_new} new jobs stored.")


def cmd_score(args):
    db.init_db()
    scorer = Scorer(load_profile(), db.get_companies_by_name())
    rows = db.get_jobs(unscored_only=not args.rescore)
    for r in rows:
        res = scorer.score(r["title"], r["description"], r["location"], r["company"])
        db.save_score(r["id"], res.overall, res.reason, res.breakdown, res.role_type)
    print(f"Scored {len(rows)} jobs.")


def cmd_shortlist(args):
    rows = [r for r in db.get_jobs() if r["fit_score"] is not None and r["status"] not in ("applied", "skipped")]
    buckets = {"HIGH": [], "REVIEW": [], "SKIP": []}
    for r in rows:
        buckets[tier_for(r["fit_score"])].append(r)

    def show(name, items, limit):
        print(f"\n{name} ({len(items)})")
        for r in items[:limit]:
            print(f"  {r['fit_score']:.1f} | {r['title']} | {r['company']} | {r['location']}")
            if args.why:
                print(f"        {r['fit_reason']}")
                print(f"        {r['url']}")

    show("HIGH PRIORITY", buckets["HIGH"], args.limit)
    show("REVIEW", buckets["REVIEW"], args.limit)
    print(f"\nSKIP ({len(buckets['SKIP'])}) hidden. Run `python run.py dashboard` to browse everything.")


def cmd_daily(args):
    print("== Fetching ==")
    cmd_fetch(args)
    print("\n== Scoring ==")
    cmd_score(args)
    print("\n== Shortlist ==")
    cmd_shortlist(args)


def cmd_export(args):
    n = db.export_slim(config.SLIM_DB_PATH, config.REVIEW_MIN, config.SLIM_MAX_DESCRIPTION)
    size = config.SLIM_DB_PATH.stat().st_size / 1e6
    print(f"Exported {n} jobs to {config.SLIM_DB_PATH} ({size:.1f} MB)")


def cmd_dashboard(args):
    app = Path(__file__).parent / "src" / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app)])


def cmd_check_sources(args):
    for s in load_sources():
        label = f"{s['collector']}:{s['board']}"
        try:
            jobs = get_collector(s["collector"]).fetch(s)
            sample = jobs[0].title if jobs else "-"
            print(f"  [ok]   {label:<28} {len(jobs):>4} jobs   e.g. {sample}")
        except Exception as e:
            print(f"  [FAIL] {label:<28} {e}")
        time.sleep(config.DELAY_BETWEEN_SOURCES)


def cmd_explain(args):
    scorer = Scorer(load_profile(), db.get_companies_by_name())
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE id=?", (args.job_id,)).fetchone()
    if not r:
        sys.exit(f"No job with id {args.job_id}")
    res = scorer.score(r["title"], r["description"], r["location"], r["company"])
    print(f"{r['title']} | {r['company']} | {r['location']}\n{r['url']}\n")
    for dim, v in res.breakdown.items():
        print(f"  {dim:<16} {v['score']:>2}/10  (w={config.WEIGHTS[dim]})  {v['note']}")
    print(f"\nOverall: {res.overall}  -> {res.tier}\n{res.reason}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    p = sub.add_parser("score"); p.add_argument("--rescore", action="store_true"); p.set_defaults(fn=cmd_score)
    p = sub.add_parser("shortlist"); p.add_argument("--limit", type=int, default=25); p.add_argument("--why", action="store_true"); p.set_defaults(fn=cmd_shortlist)
    p = sub.add_parser("daily"); p.add_argument("--rescore", action="store_true"); p.add_argument("--limit", type=int, default=25); p.add_argument("--why", action="store_true"); p.set_defaults(fn=cmd_daily)
    sub.add_parser("dashboard").set_defaults(fn=cmd_dashboard)
    sub.add_parser("export").set_defaults(fn=cmd_export)
    sub.add_parser("check-sources").set_defaults(fn=cmd_check_sources)
    p = sub.add_parser("explain"); p.add_argument("job_id", type=int); p.set_defaults(fn=cmd_explain)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
