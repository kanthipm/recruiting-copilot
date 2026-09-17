"""SQLite storage. One connection per call keeps this trivially safe for CLI + Streamlit."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT,
    url           TEXT NOT NULL UNIQUE,
    description   TEXT,
    source        TEXT,
    date_posted   TEXT,
    date_found    TEXT,
    role_type     TEXT,
    fit_score     REAL,
    fit_reason    TEXT,
    fit_breakdown TEXT,             -- JSON: {dimension: {"score": n, "note": "..."}}
    status        TEXT DEFAULT 'new' -- new | saved | applied | skipped
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(fit_score);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);

CREATE TABLE IF NOT EXISTS companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    website      TEXT,
    industry     TEXT,
    company_type TEXT,
    stage        TEXT,
    quality      INTEGER,          -- your 1-5 rating from sources.json
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER NOT NULL REFERENCES jobs(id),
    status       TEXT,
    date_applied TEXT,
    notes        TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        # lightweight migrations for DBs created by older versions
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(companies)")}
        for col, typ in (("stage", "TEXT"), ("quality", "INTEGER")):
            if col not in existing:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {typ}")


# ---------- companies ----------

def upsert_company(conn, source: dict):
    conn.execute(
        """INSERT INTO companies (name, website, industry, company_type, stage, quality, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             website=excluded.website, industry=excluded.industry, company_type=excluded.company_type,
             stage=excluded.stage, quality=excluded.quality""",
        (source["company"], source.get("website"), source.get("industry"),
         source.get("company_type"), source.get("stage"), source.get("quality"), source.get("notes")),
    )


# ---------- jobs ----------

def insert_jobs(jobs) -> int:
    """Insert new jobs; existing URLs are ignored. Returns number of new rows."""
    found = now_iso()
    new = 0
    with connect() as conn:
        for job in jobs:
            cur = conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (title, company, location, url, description, source, date_posted, date_found)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (job.title, job.company, job.location, job.url, job.description,
                 job.source, job.date_posted, found),
            )
            new += cur.rowcount
    return new


def get_jobs(unscored_only: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM jobs"
    if unscored_only:
        sql += " WHERE fit_score IS NULL"
    sql += " ORDER BY fit_score DESC, date_found DESC"
    with connect() as conn:
        return conn.execute(sql).fetchall()


def get_companies_by_name() -> dict[str, dict]:
    with connect() as conn:
        return {r["name"]: dict(r) for r in conn.execute("SELECT * FROM companies")}


def save_score(job_id: int, score: float, reason: str, breakdown: dict, role_type: str):
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET fit_score=?, fit_reason=?, fit_breakdown=?, role_type=? WHERE id=?",
            (score, reason, json.dumps(breakdown), role_type, job_id),
        )


def save_scores(results: list[tuple]):
    """results: [(job_id, score, reason, breakdown_dict, role_type), ...] saved in one transaction."""
    with connect() as conn:
        conn.executemany(
            "UPDATE jobs SET fit_score=?, fit_reason=?, fit_breakdown=?, role_type=? WHERE id=?",
            [(s, r, json.dumps(b), rt, jid) for jid, s, r, b, rt in results],
        )


def set_status(job_id: int, status: str, notes: str = ""):
    with connect() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        if status == "applied":
            conn.execute(
                "INSERT INTO applications (job_id, status, date_applied, notes) VALUES (?, ?, ?, ?)",
                (job_id, "applied", now_iso()[:10], notes),
            )


def stats() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        scored = conn.execute("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL").fetchone()[0]
        companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    return {"jobs": total, "scored": scored, "companies": companies}


def export_slim(dest, min_score: float, max_desc: int) -> int:
    """Write a small copy of the DB (jobs >= min_score, trimmed descriptions) for hosting. Returns job count."""
    dest = str(dest)
    with connect() as conn:
        conn.execute("ATTACH DATABASE ? AS slim", (dest,))
        for stmt in SCHEMA.split(";"):
            stmt = stmt.strip()
            if stmt.startswith("CREATE TABLE"):
                conn.execute(stmt.replace("CREATE TABLE IF NOT EXISTS ", "CREATE TABLE IF NOT EXISTS slim."))
        conn.execute("DELETE FROM slim.jobs")
        conn.execute("DELETE FROM slim.companies")
        conn.execute("DELETE FROM slim.applications")
        conn.execute("INSERT INTO slim.companies SELECT * FROM companies")
        conn.execute(
            """INSERT INTO slim.jobs
               SELECT id, title, company, location, url, substr(description, 1, ?), source, date_posted,
                      date_found, role_type, fit_score, fit_reason, fit_breakdown, status
               FROM jobs WHERE fit_score >= ?""",
            (max_desc, min_score),
        )
        conn.execute("INSERT INTO slim.applications SELECT * FROM applications")
        n = conn.execute("SELECT COUNT(*) FROM slim.jobs").fetchone()[0]
        conn.commit()
        conn.execute("DETACH DATABASE slim")
    return n
